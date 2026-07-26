import sys
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Session
from timetable.models import Timetable, TimetableSlot
from scheduling.engine.models_io import load_schedule_input, placements_to_slot_dicts
from scheduling.engine.algorithm import run_scheduler


class Command(BaseCommand):
    help = 'Generate a new timetable version for a given session'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session',
            type=str,
            required=True,
            help='Name or primary key of the session',
        )
        parser.add_argument('--max-restarts', type=int, default=10, help='Maximum restarts for the algorithm')

    def handle(self, *args, **options):
        session_arg = options['session']
        max_restarts = options['max_restarts']

        try:
            if session_arg.isdigit():
                session = Session.objects.get(pk=int(session_arg))
            else:
                session = Session.objects.get(name=session_arg)
        except Session.DoesNotExist:
            raise CommandError(f"Session '{session_arg}' does not exist (tried name/pk).")
        except Session.MultipleObjectsReturned:
            raise CommandError(
                f"Multiple sessions named '{session_arg}'. Pass the primary key instead."
            )

        self.stdout.write(f"Loading input for session {session.name}...")

        try:
            schedule_input = load_schedule_input(session.id)
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
            # Get latest version number for this session
            latest_timetable = Timetable.objects.filter(session=session).order_by('-version').first()
            version = (latest_timetable.version + 1) if latest_timetable else 1

            timetable = Timetable.objects.create(
                session=session,
                version=version,
                status=Timetable.Status.DRAFT,
                penalty_score=result.penalty
            )

            slot_dicts = placements_to_slot_dicts(result, schedule_input, timetable_id=timetable.id)

            TimetableSlot.objects.bulk_create(
                [TimetableSlot(**d) for d in slot_dicts]
            )

        self.stdout.write(self.style.SUCCESS(f"Successfully generated timetable v{timetable.version}."))
