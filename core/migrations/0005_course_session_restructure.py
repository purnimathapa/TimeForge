# Generated manually for Semester → Session rename.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_require_school_on_core_models'),
        # Wait until historical FKs to Semester exist before renaming the model.
        ('academics', '0004_subject_teacher_departments_m2m'),
        ('scheduling', '0002_constraint_max_consecutive_periods_and_more'),
        ('timetable', '0005_edit_lock_and_teacher_unique'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Semester',
            new_name='Session',
        ),
        migrations.AlterModelOptions(
            name='session',
            options={'ordering': ['-start_date']},
        ),
        migrations.RemoveField(
            model_name='session',
            name='code',
        ),
        migrations.AlterField(
            model_name='session',
            name='name',
            field=models.CharField(
                help_text='Display label, e.g. Fall 2026',
                max_length=100,
            ),
        ),
        migrations.AlterField(
            model_name='session',
            name='school',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sessions',
                to='core.school',
            ),
        ),
    ]
