"""Reusable mixins for tenant-scoped class-based views."""

from core.tenant import filter_by_school, require_school


class SchoolScopedMixin:
    """Filter get_queryset() to the current tenant."""

    school_lookup = 'school'

    def get_queryset(self):
        qs = super().get_queryset()
        return filter_by_school(qs, self.request, self.school_lookup)


class SchoolFormMixin:
    """Pass request.school into forms and assign it on direct-FK creates."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['school'] = getattr(self.request, 'school', None)
        return kwargs

    def form_valid(self, form):
        school = getattr(self.request, 'school', None)
        if school is not None and hasattr(form.instance, 'school_id') and form.instance.school_id is None:
            form.instance.school = school
        elif school is None and not self.request.user.is_superuser:
            require_school(self.request)
        return super().form_valid(form)
