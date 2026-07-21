"""Reusable mixins for tenant-scoped class-based views."""

import inspect
from collections import Counter

from django.contrib import messages
from django.db.models import CASCADE, PROTECT, RESTRICT, ProtectedError, RestrictedError
from django.shortcuts import redirect

from core.tenant import filter_by_school, require_school


class SchoolScopedMixin:
    """Filter get_queryset() to the current tenant."""

    school_lookup = 'school'

    def get_queryset(self):
        qs = super().get_queryset()
        return filter_by_school(qs, self.request, self.school_lookup)


def _form_accepts_school(form_class):
    """True if form_class.__init__ accepts a ``school`` keyword argument.

    DeleteView uses a plain ``django.forms.Form`` (no ``school`` kwarg), so we
    must not inject ``school`` there — doing so raises TypeError under Django's
    form-based DeleteView. CreateView/UpdateView use school-aware ModelForms.
    """
    if form_class is None:
        return False
    try:
        signature = inspect.signature(form_class.__init__)
    except (TypeError, ValueError):
        return False
    for parameter in signature.parameters.values():
        if parameter.name == 'school':
            return True
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return True
    return False


class SchoolFormMixin:
    """Pass request.school into forms and assign it on direct-FK creates."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        form_class = self.get_form_class()
        if _form_accepts_school(form_class):
            kwargs['school'] = getattr(self.request, 'school', None)
        return kwargs

    def form_valid(self, form):
        school = getattr(self.request, 'school', None)
        if school is not None and hasattr(form.instance, 'school_id') and form.instance.school_id is None:
            form.instance.school = school
        elif school is None and not self.request.user.is_superuser:
            require_school(self.request)
        return super().form_valid(form)


def _related_blockers(obj, *, _depth=0, _max_depth=1):
    """Return PROTECT/RESTRICT reverse relations that would block deleting obj.

    Walks one level of CASCADE children as well (e.g. Section → ClassSession →
    TimetableSlot), so the confirm page can warn about nested blockers.
    Does not mutate the database.
    """
    merged = {}

    def _add(label, count, samples):
        entry = merged.setdefault(label, {'label': label, 'count': 0, 'samples': []})
        entry['count'] += count
        for sample in samples:
            if sample not in entry['samples'] and len(entry['samples']) < 5:
                entry['samples'].append(sample)

    for relation in obj._meta.related_objects:
        on_delete = getattr(relation, 'on_delete', None)
        accessor = relation.get_accessor_name()
        if not accessor:
            continue
        related = getattr(obj, accessor, None)
        if related is None:
            continue

        if on_delete in (PROTECT, RESTRICT):
            if relation.one_to_one:
                try:
                    if not hasattr(related, 'all'):
                        _add(
                            str(relation.related_model._meta.verbose_name_plural),
                            1,
                            [str(related)],
                        )
                except Exception:
                    continue
            else:
                qs = related.all()
                count = qs.count()
                if count:
                    samples = [str(item) for item in qs[:5]]
                    _add(str(relation.related_model._meta.verbose_name_plural), count, samples)

        elif on_delete == CASCADE and _depth < _max_depth and not relation.one_to_one:
            for child in related.all()[:100]:
                for blocker in _related_blockers(child, _depth=_depth + 1, _max_depth=_max_depth):
                    _add(blocker['label'], blocker['count'], blocker['samples'])

    return list(merged.values())


class ProtectedDeleteMixin:
    """Delete-view mixin that reports success and handles FK protection.

    Under Django's form-based DeleteView the deletion happens in form_valid(),
    not in delete(). This mixin performs the delete there, adds a success
    message, and turns ProtectedError/RestrictedError into a user-friendly
    message that names the records still depending on the object — without ever
    bypassing database integrity.
    """

    success_message = "Deleted successfully."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = getattr(self, 'object', None) or ctx.get('object')
        if obj is not None:
            ctx['delete_blockers'] = _related_blockers(obj)
        return ctx

    def form_valid(self, form):
        obj = self.object
        label = str(obj)
        success_url = self.get_success_url()
        try:
            self.perform_delete(obj)
        except (ProtectedError, RestrictedError) as exc:
            messages.error(self.request, self._protected_message(label, exc))
            return redirect(success_url)
        messages.success(self.request, self.success_message)
        return redirect(success_url)

    def perform_delete(self, obj):
        """Hook for subclasses that need a custom delete target (e.g. User)."""
        obj.delete()

    def _protected_message(self, label, exc):
        related = getattr(exc, 'protected_objects', None)
        if related is None:
            related = getattr(exc, 'restricted_objects', [])
        related = list(related)

        counts = Counter(str(obj._meta.verbose_name_plural) for obj in related)
        samples_by_type = {}
        for obj in related:
            key = str(obj._meta.verbose_name_plural)
            samples_by_type.setdefault(key, [])
            if len(samples_by_type[key]) < 3:
                samples_by_type[key].append(str(obj))

        if counts:
            parts = []
            for name, count in counts.items():
                sample = samples_by_type.get(name) or []
                if sample:
                    shown = ", ".join(sample)
                    extra = f" (e.g. {shown})" if count <= 3 else f" (e.g. {shown}, …)"
                    parts.append(f"{count} {name}{extra}")
                else:
                    parts.append(f"{count} {name}")
            detail = "; ".join(parts)
            return (
                f"Cannot delete “{label}” because other records still "
                f"depend on it: {detail}. Remove or reassign those records first."
            )
        return (
            f"Cannot delete “{label}” because other records still "
            f"depend on it. Remove or reassign those records first."
        )
