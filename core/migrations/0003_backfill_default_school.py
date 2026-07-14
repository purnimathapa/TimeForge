# Migration 2 of 3 (09A): backfill Default School for existing rows.
#
# Creates School(name="Default School", code="default") and assigns it to every
# existing Department, Room, Semester, and non-superuser User that lacks school_id.
# Superusers keep school=NULL for cross-tenant platform access (see docs/MULTI_TENANCY.md).

from django.db import migrations


DEFAULT_SCHOOL_NAME = 'Default School'
DEFAULT_SCHOOL_CODE = 'default'


def forwards(apps, schema_editor):
    School = apps.get_model('core', 'School')
    Department = apps.get_model('core', 'Department')
    Room = apps.get_model('core', 'Room')
    Semester = apps.get_model('core', 'Semester')
    User = apps.get_model('accounts', 'User')

    school, _created = School.objects.get_or_create(
        code=DEFAULT_SCHOOL_CODE,
        defaults={
            'name': DEFAULT_SCHOOL_NAME,
            'is_active': True,
        },
    )

    Department.objects.filter(school__isnull=True).update(school=school)
    Room.objects.filter(school__isnull=True).update(school=school)
    Semester.objects.filter(school__isnull=True).update(school=school)
    User.objects.filter(is_superuser=False, school__isnull=True).update(school=school)


def backwards(apps, schema_editor):
    School = apps.get_model('core', 'School')
    Department = apps.get_model('core', 'Department')
    Room = apps.get_model('core', 'Room')
    Semester = apps.get_model('core', 'Semester')
    User = apps.get_model('accounts', 'User')

    try:
        school = School.objects.get(code=DEFAULT_SCHOOL_CODE)
    except School.DoesNotExist:
        return

    Department.objects.filter(school=school).update(school=None)
    Room.objects.filter(school=school).update(school=None)
    Semester.objects.filter(school=school).update(school=None)
    User.objects.filter(school=school).update(school=None)
    school.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_user_school_nullable'),
        ('core', '0002_school_and_nullable_tenant_fks'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
