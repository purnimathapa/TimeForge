from django.core.management.base import BaseCommand
from scheduling.models import TimeSlot
import datetime


class Command(BaseCommand):
    help = 'Seeds the weekly TimeSlots: 07:00 to 17:00 with an 11:00 to 12:00 lunch break, Mon-Fri'

    def handle(self, *args, **kwargs):
        # Class periods run 07:00 to 17:00 (Monday to Friday) with a one-hour
        # lunch break at 11:00 to 12:00. Because the break is a gap between
        # periods (not a schedulable slot), no class is ever placed during lunch.
        days = [
            TimeSlot.DayOfWeek.MONDAY,
            TimeSlot.DayOfWeek.TUESDAY,
            TimeSlot.DayOfWeek.WEDNESDAY,
            TimeSlot.DayOfWeek.THURSDAY,
            TimeSlot.DayOfWeek.FRIDAY,
        ]

        periods = [
            (1, datetime.time(7, 0), datetime.time(9, 0)),
            (2, datetime.time(9, 0), datetime.time(11, 0)),
            # Lunch break 11:00 to 12:00 (no period scheduled here).
            (3, datetime.time(12, 0), datetime.time(14, 0)),
            (4, datetime.time(14, 0), datetime.time(16, 0)),
            (5, datetime.time(16, 0), datetime.time(17, 0)),
        ]
        valid_period_numbers = {p[0] for p in periods}

        created_count = 0
        updated_count = 0
        for day in days:
            for p_num, start, end in periods:
                obj, created = TimeSlot.objects.update_or_create(
                    day_of_week=day,
                    period_number=p_num,
                    defaults={
                        'start_time': start,
                        'end_time': end,
                        'is_active': True,
                    },
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        # Deactivate (do not delete) any legacy periods outside the new scheme so
        # existing timetable rows that still reference them are not broken.
        deactivated = (
            TimeSlot.objects
            .exclude(period_number__in=valid_period_numbers)
            .filter(is_active=True)
            .update(is_active=False)
        )

        self.stdout.write(self.style.SUCCESS(
            f'TimeSlots seeded. Created: {created_count}, updated: {updated_count}, '
            f'legacy deactivated: {deactivated}. '
            f'Lunch break is 11:00 to 12:00. Re-generate timetables to use the new periods.'
        ))
