# Clear dependents; retarget Section.semester → core.session in state.

import django.db.models.deletion
from django.db import migrations, models


def clear_section_dependents(apps, schema_editor):
    ClassRepProfile = apps.get_model('academics', 'ClassRepProfile')
    ClassSession = apps.get_model('academics', 'ClassSession')
    DraftMove = apps.get_model('timetable', 'DraftMove')
    DraftChangeSet = apps.get_model('timetable', 'DraftChangeSet')
    TimetableSlot = apps.get_model('timetable', 'TimetableSlot')
    Timetable = apps.get_model('timetable', 'Timetable')
    Constraint = apps.get_model('scheduling', 'Constraint')
    Section = apps.get_model('academics', 'Section')

    DraftMove.objects.all().delete()
    DraftChangeSet.objects.all().delete()
    TimetableSlot.objects.all().delete()
    Timetable.objects.all().delete()
    Constraint.objects.all().delete()
    ClassRepProfile.objects.all().delete()
    ClassSession.objects.all().delete()
    Section.objects.all().delete()


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('core', '0005_course_session_restructure'),
        ('academics', '0004_subject_teacher_departments_m2m'),
        ('scheduling', '0003_course_session_restructure'),
        ('timetable', '0005_edit_lock_and_teacher_unique'),
    ]

    operations = [
        migrations.AlterField(
            model_name='section',
            name='semester',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sections',
                to='core.session',
            ),
        ),
        migrations.RunPython(clear_section_dependents, migrations.RunPython.noop),
    ]
