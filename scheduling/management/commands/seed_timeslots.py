from django.core.management.base import BaseCommand
from scheduling.models import TimeSlot
import datetime

class Command(BaseCommand):
    help = 'Seeds the database with standard weekly TimeSlots'

    def handle(self, *args, **kwargs):
        # 8 periods per day, Monday to Friday
        # Periods: 
        # 1: 08:00 - 08:50
        # 2: 09:00 - 09:50
        # 3: 10:00 - 10:50
        # 4: 11:00 - 11:50
        # 5: 12:00 - 12:50
        # 6: 13:00 - 13:50
        # 7: 14:00 - 14:50
        # 8: 15:00 - 15:50
        
        days = [
            TimeSlot.DayOfWeek.MONDAY,
            TimeSlot.DayOfWeek.TUESDAY,
            TimeSlot.DayOfWeek.WEDNESDAY,
            TimeSlot.DayOfWeek.THURSDAY,
            TimeSlot.DayOfWeek.FRIDAY,
        ]

        periods = [
            (1, datetime.time(8, 0), datetime.time(8, 50)),
            (2, datetime.time(9, 0), datetime.time(9, 50)),
            (3, datetime.time(10, 0), datetime.time(10, 50)),
            (4, datetime.time(11, 0), datetime.time(11, 50)),
            (5, datetime.time(12, 0), datetime.time(12, 50)),
            (6, datetime.time(13, 0), datetime.time(13, 50)),
            (7, datetime.time(14, 0), datetime.time(14, 50)),
            (8, datetime.time(15, 0), datetime.time(15, 50)),
        ]

        created_count = 0
        for day in days:
            for p_num, start, end in periods:
                _, created = TimeSlot.objects.get_or_create(
                    day_of_week=day,
                    period_number=p_num,
                    defaults={
                        'start_time': start,
                        'end_time': end,
                        'is_active': True
                    }
                )
                if created:
                    created_count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully seeded TimeSlots. Created: {created_count}'))
