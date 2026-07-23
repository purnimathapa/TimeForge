from django.db import migrations, models


def copy_subject_departments(apps, schema_editor):
    Subject = apps.get_model('academics', 'Subject')
    for subject in Subject.objects.all():
        if subject.department_id:
            subject.departments.add(subject.department_id)


def copy_teacher_departments(apps, schema_editor):
    TeacherProfile = apps.get_model('academics', 'TeacherProfile')
    for teacher in TeacherProfile.objects.all():
        if teacher.department_id:
            teacher.departments.add(teacher.department_id)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_require_school_on_core_models'),
        ('academics', '0003_teacherprofile_is_visiting_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='subject',
            name='departments',
            field=models.ManyToManyField(
                help_text='A subject may be offered by one or more departments.',
                related_name='subjects',
                to='core.department',
            ),
        ),
        migrations.AddField(
            model_name='teacherprofile',
            name='departments',
            field=models.ManyToManyField(
                blank=True,
                help_text='A teacher may be affiliated with one or more departments.',
                related_name='teachers',
                to='core.department',
            ),
        ),
        migrations.RunPython(copy_subject_departments, migrations.RunPython.noop),
        migrations.RunPython(copy_teacher_departments, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='subject',
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name='subject',
            name='department',
        ),
        migrations.RemoveField(
            model_name='teacherprofile',
            name='department',
        ),
    ]
