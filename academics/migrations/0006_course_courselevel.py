# Replace Section with Course + CourseLevel; rewire ClassSession / ClassRep.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_course_session_restructure'),
        ('academics', '0005_clear_section_dependents'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Course',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('code', models.CharField(max_length=30)),
                ('is_active', models.BooleanField(default=True)),
                ('department', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='courses',
                    to='core.department',
                )),
            ],
            options={
                'ordering': ['name'],
                'unique_together': {('code', 'department')},
            },
        ),
        migrations.CreateModel(
            name='CourseLevel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('level', models.PositiveSmallIntegerField(
                    choices=[
                        (1, 'Semester 1'), (2, 'Semester 2'), (3, 'Semester 3'), (4, 'Semester 4'),
                        (5, 'Semester 5'), (6, 'Semester 6'), (7, 'Semester 7'), (8, 'Semester 8'),
                    ],
                )),
                ('student_count', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('course', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='levels',
                    to='academics.course',
                )),
            ],
            options={
                'ordering': ['course__name', 'level'],
                'unique_together': {('course', 'level')},
            },
        ),
        migrations.RemoveField(
            model_name='classrepprofile',
            name='section',
        ),
        migrations.RemoveField(
            model_name='classsession',
            name='section',
        ),
        migrations.AddField(
            model_name='classrepprofile',
            name='course_level',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='class_reps',
                to='academics.courselevel',
            ),
        ),
        migrations.AddField(
            model_name='classsession',
            name='course_level',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='class_sessions',
                to='academics.courselevel',
            ),
        ),
        migrations.AddField(
            model_name='classsession',
            name='session',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='class_sessions',
                to='core.session',
            ),
        ),
        migrations.DeleteModel(
            name='Section',
        ),
    ]
