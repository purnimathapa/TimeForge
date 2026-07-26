from django.db import migrations, models


def rename_constraint_types(apps, schema_editor):
    Constraint = apps.get_model('scheduling', 'Constraint')
    Constraint.objects.filter(constraint_type='MAX_DAILY_HOURS').update(
        constraint_type='MAX_DAILY_PERIODS',
    )
    Constraint.objects.filter(constraint_type='MAX_WEEKLY_HOURS').update(
        constraint_type='MAX_WEEKLY_PERIODS',
    )


def revert_constraint_types(apps, schema_editor):
    Constraint = apps.get_model('scheduling', 'Constraint')
    Constraint.objects.filter(constraint_type='MAX_DAILY_PERIODS').update(
        constraint_type='MAX_DAILY_HOURS',
    )
    Constraint.objects.filter(constraint_type='MAX_WEEKLY_PERIODS').update(
        constraint_type='MAX_WEEKLY_HOURS',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0005_remove_custom_add_max_weekly_hours'),
    ]

    operations = [
        migrations.RunPython(rename_constraint_types, revert_constraint_types),
        migrations.AlterField(
            model_name='constraint',
            name='constraint_type',
            field=models.CharField(
                choices=[
                    ('ROOM_TYPE_REQUIRED', 'Room Type Required'),
                    ('MAX_DAILY_PERIODS', 'Max Daily Periods'),
                    ('MAX_WEEKLY_PERIODS', 'Max Weekly Periods'),
                    ('NO_ADJACENT_GAPS', 'No Adjacent Gaps'),
                    ('MAX_CONSECUTIVE_PERIODS', 'Max Consecutive Periods'),
                    ('PREFERRED_TEACHING_TIME', 'Preferred Teaching Time'),
                ],
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='constraint',
            name='max_daily_periods',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Maximum teaching periods allowed in one day (Max Daily Periods).',
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name='constraint',
            name='max_weekly_periods',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Maximum teaching periods allowed across the week (Max Weekly Periods).',
                null=True,
            ),
        ),
    ]
