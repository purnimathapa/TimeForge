import sys
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Semester
from timetable.models import Timetable, TimetableSlot
from scheduling.engine.models_io import load_schedule_input, placements_to_slot_dicts
from scheduling.engine.algorithm import run_scheduler
from scheduling.engine.constraints import compute_penalty

class Command(BaseCommand):
    help = 'Generate a new timetable version for a given semester'

    def add_arguments(self, parser):
        parser.add_argument('--semester', type=str, required=True, help='Code of the semester')
        parser.add_argument('--max-restarts', type=int, default=10, help='Maximum restarts for the algorithm')

    def handle(self, *args, **options):
        semester_code = options['semester']
        max_restarts = options['max_restarts']

        try:
            semester = Semester.objects.get(code=semester_code)
        except Semester.DoesNotExist:
            raise CommandError(f"Semester with code '{semester_code}' does not exist.")

        self.stdout.write(f"Loading input for semester {semester.name}...")
        
        try:
            schedule_input = load_schedule_input(semester.id)
        except ValueError as e:
            raise CommandError(str(e))

        self.stdout.write("Running scheduler algorithm...")
        result = run_scheduler(schedule_input, max_restarts=max_restarts)

        if not result.success:
            self.stderr.write(self.style.ERROR("Algorithm failed to find a hard-feasible schedule."))
            if result.failure_reason:
                self.stderr.write(result.failure_reason)
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS("Schedule found! Persisting to database..."))

        with transaction.atomic():
            # Get latest version number for this semester
            latest_timetable = Timetable.objects.filter(semester=semester).order_by('-version').first()
            version = (latest_timetable.version + 1) if latest_timetable else 1

            timetable = Timetable.objects.create(
                semester=semester,
                version=version,
                status=Timetable.Status.DRAFT,
                penalty_score=result.penalty
            )

            slot_dicts = placements_to_slot_dicts(result, schedule_input, timetable_id=timetable.id)
            
            TimetableSlot.objects.bulk_create(
                [TimetableSlot(**d) for d in slot_dicts]
            )

        self.stdout.write(self.style.SUCCESS(f"Successfully generated timetable v{timetable.version} (Penalty: {timetable.penalty_score})."))
