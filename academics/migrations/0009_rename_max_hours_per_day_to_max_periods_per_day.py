from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0008_course_level_offering'),
    ]

    operations = [
        migrations.RenameField(
            model_name='teacherprofile',
            old_name='max_hours_per_day',
            new_name='max_periods_per_day',
        ),
        migrations.AlterField(
            model_name='teacherprofile',
            name='max_periods_per_day',
            field=models.PositiveIntegerField(
                default=4,
                help_text='Maximum teaching periods this teacher may have in one day.',
            ),
        ),
    ]
