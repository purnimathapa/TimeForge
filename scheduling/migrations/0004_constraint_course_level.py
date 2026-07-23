# Add Constraint.course_level now that CourseLevel exists.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0006_course_courselevel'),
        ('scheduling', '0003_course_session_restructure'),
    ]

    operations = [
        migrations.AddField(
            model_name='constraint',
            name='course_level',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='academics.courselevel',
            ),
        ),
    ]
