# Migration 1 of 3 (09A): School model and nullable tenant FKs on core models.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='School',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True)),
                ('code', models.SlugField(max_length=50, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='department',
            name='school',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='departments',
                to='core.school',
            ),
        ),
        migrations.AddField(
            model_name='room',
            name='school',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='rooms',
                to='core.school',
            ),
        ),
        migrations.AddField(
            model_name='semester',
            name='school',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='semesters',
                to='core.school',
            ),
        ),
        migrations.AlterField(
            model_name='room',
            name='department',
            field=models.ForeignKey(
                blank=True,
                help_text='Optional informational link; tenant ownership is via school.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rooms',
                to='core.department',
            ),
        ),
    ]
