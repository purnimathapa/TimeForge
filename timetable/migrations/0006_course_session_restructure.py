# Timetable.semester → Timetable.session

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0006_course_courselevel'),
        ('core', '0005_course_session_restructure'),
        ('timetable', '0005_edit_lock_and_teacher_unique'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='timetable', name='semester'),
                migrations.AddField(
                    model_name='timetable',
                    name='session',
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='timetables',
                        to='core.session',
                    ),
                ),
                migrations.AlterUniqueTogether(
                    name='timetable',
                    unique_together={('session', 'version')},
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE timetable_timetable '
                        'RENAME COLUMN semester_id TO session_id;'
                    ),
                    reverse_sql=(
                        'ALTER TABLE timetable_timetable '
                        'RENAME COLUMN session_id TO semester_id;'
                    ),
                ),
            ],
        ),
        migrations.AlterField(
            model_name='timetable',
            name='version',
            field=models.PositiveIntegerField(
                default=1,
                help_text='Auto-incremented per session. Version 1 is the first generation.',
            ),
        ),
    ]
