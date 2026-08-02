"""Shared helpers for tests that need a tenant school.

Most integration and tenant-isolation tests call get_test_school() to create
an isolated School row per test class, avoiding collisions on unique code/name
fields. Used by timetable, dashboard, core tenant tests, and others.

For release-blocker multi-tenant checks, see core.tests.test_tenant_isolation.
"""

from core.models import School

_school_counter = 0


def get_test_school(**kwargs):
    global _school_counter
    _school_counter += 1
    defaults = {
        'name': kwargs.pop('name', f'Test School {_school_counter}'),
        'code': kwargs.pop('code', f'test-school-{_school_counter}'),
        'is_active': True,
    }
    defaults.update(kwargs)
    return School.objects.create(**defaults)
