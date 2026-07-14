"""Tenant scoping helpers for school-isolated querysets."""

from django.core.exceptions import PermissionDenied


def school_filter(qs, request, *, field='school'):
    """
    Filter a queryset to the request tenant.

    Superusers with no assigned school see all rows (platform operator mode).
    Authenticated users with a school see only their tenant's rows.
    Everyone else gets an empty queryset.
    """
    if request.user.is_authenticated and request.user.is_superuser and getattr(request, 'school', None) is None:
        return qs
    if getattr(request, 'school', None) is None:
        return qs.none()
    return qs.filter(**{field: request.school})


def filter_by_school(qs, request, lookup='school'):
    """Alias for school_filter with an explicit ORM lookup path."""
    return school_filter(qs, request, field=lookup)


def require_school(request):
    """
    Return the tenant school or raise PermissionDenied.

    Superusers without an assigned school may operate cross-tenant and receive None.
    """
    school = getattr(request, 'school', None)
    if school is not None:
        return school
    if request.user.is_authenticated and request.user.is_superuser:
        return None
    raise PermissionDenied('School context is required for this action.')
