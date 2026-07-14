# Migration 3 of 3 (09A): require school on Department, Room, Semester.
# User.school remains nullable for superusers (see docs/MULTI_TENANCY.md).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_backfill_default_school'),
    ]

    operations = [
        migrations.AlterField(
            model_name='department',
            name='school',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='departments',
                to='core.school',
            ),
        ),
        migrations.AlterField(
            model_name='room',
            name='school',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='rooms',
                to='core.school',
            ),
        ),
        migrations.AlterField(
            model_name='semester',
            name='school',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='semesters',
                to='core.school',
            ),
        ),
    ]
