# Constraint: semester → session; drop section FK (course_level added later).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_course_session_restructure'),
        ('scheduling', '0002_constraint_max_consecutive_periods_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='constraint', name='semester'),
                migrations.RemoveField(model_name='constraint', name='section'),
                migrations.AddField(
                    model_name='constraint',
                    name='session',
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='constraints',
                        to='core.session',
                    ),
                ),
                migrations.AlterField(
                    model_name='constraint',
                    name='target_type',
                    field=models.CharField(
                        choices=[
                            ('TEACHER', 'Teacher'),
                            ('COURSE_LEVEL', 'Course Level'),
                            ('ROOM', 'Room'),
                            ('SUBJECT', 'Subject'),
                            ('GLOBAL', 'Global / Session'),
                        ],
                        max_length=20,
                    ),
                ),
            ],
            database_operations=[
                # semester column already points at renamed core_session table
                migrations.RunSQL(
                    sql='ALTER TABLE scheduling_constraint RENAME COLUMN semester_id TO session_id;',
                    reverse_sql='ALTER TABLE scheduling_constraint RENAME COLUMN session_id TO semester_id;',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE scheduling_constraint DROP COLUMN IF EXISTS section_id CASCADE;',
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
