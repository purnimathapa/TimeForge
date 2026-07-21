"""
timetable/views.py

Read-only timetable grid views filtered by Teacher, Room, and Section,
plus a soft-constraint Conflict Report view.

All grid views share a common base that:
  - selects the latest timetable (PUBLISHED preferred, else DRAFT) for the
    active semester, overridable via ?timetable_id=
  - queries TimetableSlot with select_related to avoid N+1
  - builds a {day → {period → [slot, …]}} grid structure for the template
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.text import slugify
from django.views import View
from django.views.generic import DeleteView, DetailView, ListView, TemplateView

from accounts.mixins import RoleRequiredMixin
from core.mixins import ProtectedDeleteMixin
from academics.models import TeacherProfile, Section
from core.models import Department, Room, Semester
from core.tenant import filter_by_school, school_filter
from scheduling.engine.algorithm import run_scheduler
from scheduling.engine.constraints import (
    compute_penalty,
    find_hard_violations,
    validate_single_placement,
)
from scheduling.engine.data_types import Placement
from scheduling.engine.models_io import load_schedule_input, placements_to_slot_dicts
from scheduling.models import TimeSlot, Constraint
from .exports import export_timetable_pdf, export_timetable_xlsx
from .models import (
    DraftChangeSet,
    DraftMove,
    Timetable,
    TimetableSlot,
    acquire_lock,
    is_locked_by_other,
    lock_holder_display_name,
    release_lock,
)
from .services.editor import MoveParseError, build_hypothetical_placements, parse_move_payloads


# ── Fixed subject‑colour palette (10 colours) ─────────────────────────────
# Maps subject code → index via deterministic hash so the same subject always
# gets the same colour across all views.
_COLOUR_COUNT = 10


def _subject_colour_index(subject_code: str) -> int:
    """Deterministic colour index from subject code."""
    return sum(ord(c) for c in subject_code) % _COLOUR_COUNT


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_active_semester(request):
    """Return the currently active semester for the request tenant, or None."""
    return school_filter(Semester.objects.filter(is_active=True), request).first()


def _scoped_semesters(request):
    return school_filter(Semester.objects.all(), request).order_by('-start_date', '-pk')


def _scoped_departments(request):
    return school_filter(Department.objects.filter(is_active=True), request).order_by('name')


def _get_selected_semester(request):
    """Resolve semester from ?semester_id=, else the active semester (then newest)."""
    qs = _scoped_semesters(request)
    semester_id = request.GET.get('semester_id')
    if semester_id:
        selected = qs.filter(pk=semester_id).first()
        if selected is not None:
            return selected
    return qs.filter(is_active=True).first() or qs.first()


def _get_selected_department(request):
    """Optional department from ?department_id=. None means all departments."""
    department_id = request.GET.get('department_id')
    if not department_id:
        return None
    return _scoped_departments(request).filter(pk=department_id).first()


def _scoped_timetables(request):
    return filter_by_school(Timetable.objects.all(), request, 'semester__school')


def _scoped_timetable_slots(request):
    return filter_by_school(
        TimetableSlot.objects.all(),
        request,
        'timetable__semester__school',
    )


def _scoped_draft_change_sets(request):
    return filter_by_school(
        DraftChangeSet.objects.all(),
        request,
        'timetable__semester__school',
    )


def _scoped_teacher_profiles(request):
    return filter_by_school(
        TeacherProfile.objects.filter(is_active=True),
        request,
        'user__school',
    )


def _scoped_rooms(request):
    return school_filter(Room.objects.filter(is_active=True), request)


def _scoped_sections(request, semester=None):
    qs = filter_by_school(
        Section.objects.filter(is_active=True),
        request,
        'department__school',
    )
    if semester is not None:
        qs = qs.filter(semester=semester)
    return qs


def _teachers_for_filters(request, department=None):
    qs = _scoped_teacher_profiles(request).select_related('user', 'department')
    if department is not None:
        qs = qs.filter(department=department)
    return qs.order_by('user__first_name', 'user__last_name')


def _rooms_for_filters(request, department=None):
    qs = _scoped_rooms(request).select_related('department')
    if department is not None:
        qs = qs.filter(department=department)
    return qs.order_by('name')


def _sections_for_filters(request, semester=None, department=None):
    qs = _scoped_sections(request, semester=semester).select_related('department', 'semester')
    if department is not None:
        qs = qs.filter(department=department)
    return qs.order_by('name')


def _school_id_for_request(request):
    return request.school.id if getattr(request, 'school', None) is not None else None


def _get_timetable(request, semester):
    """
    Resolve the timetable to display.

    Priority:
      1. Explicit ?timetable_id= query param
      2. Latest PUBLISHED timetable for the active semester
      3. (Admins only) Latest DRAFT timetable for the active semester

    Non-admin users never receive a DRAFT timetable.
    Returns (timetable, all_timetables_for_semester) or (None, qs).
    """
    if semester is None:
        return None, Timetable.objects.none()

    all_timetables = Timetable.objects.filter(semester=semester).order_by('-version')

    is_admin = request.user.is_authenticated and request.user.is_admin()

    timetable_id = request.GET.get('timetable_id')
    if timetable_id:
        try:
            timetable = all_timetables.get(pk=timetable_id)
        except Timetable.DoesNotExist:
            timetable = None
        if timetable and not is_admin and timetable.status != Timetable.Status.PUBLISHED:
            timetable = None
    elif is_admin:
        # Admins: prefer PUBLISHED, fall back to DRAFT
        timetable = (
            all_timetables
            .filter(status=Timetable.Status.PUBLISHED)
            .first()
        ) or (
            all_timetables
            .filter(status=Timetable.Status.DRAFT)
            .first()
        )
    else:
        # Non-admins: published timetables only
        timetable = all_timetables.filter(status=Timetable.Status.PUBLISHED).first()

    return timetable, all_timetables


def _get_base_slot_queryset(timetable):
    """
    Base queryset for TimetableSlot with all select_related joins
    to avoid N+1 queries across the grid.
    """
    return (
        TimetableSlot.objects
        .filter(timetable=timetable)
        .select_related(
            'class_session__subject',
            'class_session__section',
            'timeslot',
            'room',
            'teacher__user',
        )
        .order_by('timeslot__day_of_week', 'timeslot__period_number')
    )


def _build_grid(slots, timeslots):
    """
    Build a grid structure for the template.

    Returns
    -------
    grid : dict
        {day_of_week (int) : {period_number (int) : [slot, …]}}
    days : list[dict]
        Ordered list of {'number': int, 'name': str}
    periods : list[dict]
        Ordered list of {'number': int, 'start_time': time, 'end_time': time}
    """
    DAY_NAMES = {
        1: 'Monday',
        2: 'Tuesday',
        3: 'Wednesday',
        4: 'Thursday',
        5: 'Friday',
    }

    # Collect all active timeslots to define the grid dimensions
    active_days = sorted(set(ts.day_of_week for ts in timeslots))
    active_periods = sorted(set(ts.period_number for ts in timeslots))

    days = [{'number': d, 'name': DAY_NAMES.get(d, f'Day {d}')} for d in active_days]

    # Build period info with times from the first occurrence of each period
    period_times = {}
    for ts in timeslots:
        if ts.period_number not in period_times:
            period_times[ts.period_number] = {
                'start_time': ts.start_time,
                'end_time': ts.end_time,
            }

    periods = [
        {
            'number': p,
            'start_time': period_times[p]['start_time'],
            'end_time': period_times[p]['end_time'],
        }
        for p in active_periods
    ]

    # Flag any wall-clock gap between consecutive periods as a break (e.g. lunch),
    # so the grid can render a "Lunch break" row without it being schedulable.
    for index in range(len(periods) - 1):
        current = periods[index]
        following = periods[index + 1]
        if current['end_time'] != following['start_time']:
            current['break_after'] = {
                'start_time': current['end_time'],
                'end_time': following['start_time'],
            }

    # Build the grid dict
    grid = {d: {p: [] for p in active_periods} for d in active_days}

    for slot in slots:
        day = slot.timeslot.day_of_week
        period = slot.timeslot.period_number
        if day in grid and period in grid[day]:
            grid[day][period].append(slot)

    return grid, days, periods


def _annotate_colour(slots):
    """
    Annotate each slot with a `colour_class` attribute based on subject code.
    """
    for slot in slots:
        code = slot.class_session.subject.code
        slot.colour_class = f'subject-color-{_subject_colour_index(code)}'
    return slots


def _local_now():
    """Current datetime in the institution timezone (Asia/Kathmandu)."""
    return timezone.localtime(timezone.now())


def _model_day_of_week(dt):
    """Map a datetime to timetable day_of_week (Monday=1 … Sunday=7)."""
    return dt.weekday() + 1


def _slot_bounds_on_date(slot, target_date):
    """Return timezone-aware start/end datetimes for a slot on target_date."""
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(
        datetime.combine(target_date, slot.timeslot.start_time),
        tz,
    )
    end = timezone.make_aware(
        datetime.combine(target_date, slot.timeslot.end_time),
        tz,
    )
    return start, end


def _upcoming_slot_occurrences(slots, now=None):
    """
    Return sorted (slot, start_dt, end_dt) tuples for the next weekly occurrence
    of each slot that has not yet ended.
    """
    if now is None:
        now = _local_now()

    today = now.date()
    today_dow = _model_day_of_week(now)
    occurrences = []

    for slot in slots:
        day = slot.timeslot.day_of_week
        days_ahead = (day - today_dow) % 7
        target_date = today + timedelta(days=days_ahead)
        start, end = _slot_bounds_on_date(slot, target_date)

        if days_ahead == 0 and end <= now:
            target_date = today + timedelta(days=7)
            start, end = _slot_bounds_on_date(slot, target_date)

        if end > now:
            occurrences.append((slot, start, end))

    occurrences.sort(key=lambda row: row[1])
    return occurrences


def _format_slot_countdown(now, start, end):
    """Human-readable countdown label for the next class card."""
    if start <= now < end:
        return 'Now'

    total_seconds = int((start - now).total_seconds())
    if total_seconds < 60:
        return 'in less than a minute'

    minutes = total_seconds // 60
    if minutes < 60:
        suffix = 's' if minutes != 1 else ''
        return f'in {minutes} minute{suffix}'

    hours = minutes // 60
    remaining_minutes = minutes % 60
    hour_suffix = 's' if hours != 1 else ''
    if remaining_minutes:
        return f'in {hours} hour{hour_suffix} {remaining_minutes} min'
    return f'in {hours} hour{hour_suffix}'


def _resolve_next_slot(slots, now=None):
    """Return (slot, countdown_label) for the next upcoming class, or (None, '')."""
    occurrences = _upcoming_slot_occurrences(slots, now=now)
    if not occurrences:
        return None, ''
    slot, start, end = occurrences[0]
    if now is None:
        now = _local_now()
    return slot, _format_slot_countdown(now, start, end)


def _today_slots(slots, now=None):
    """Slots scheduled for the current weekday, ordered by period."""
    if now is None:
        now = _local_now()
    today_dow = _model_day_of_week(now)
    return sorted(
        [slot for slot in slots if slot.timeslot.day_of_week == today_dow],
        key=lambda slot: slot.timeslot.period_number,
    )


def _slots_to_placements(slots):
    """Convert persisted timetable slots into engine Placement dataclasses."""
    return [
        Placement(
            activity_id=slot.class_session_id,
            timeslot_id=slot.timeslot_id,
            room_id=slot.room_id,
        )
        for slot in slots
    ]


def _json_body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return None


def _edit_lock_denied_response(lock):
    holder = lock_holder_display_name(lock)
    return JsonResponse({
        'ok': False,
        'error': f'Timetable is being edited by {holder}. Try again after the lock expires.',
        'locked_by': holder,
    }, status=409)


def _edit_lock_context(timetable, user):
    """Grid template context for concurrent-edit awareness."""
    blocked, lock = is_locked_by_other(timetable, user)
    return {
        'edit_lock_held_by_other': blocked,
        'edit_lock_holder': lock_holder_display_name(lock) if blocked else '',
    }


# ── Base Grid View ─────────────────────────────────────────────────────────

class BaseTimetableGridView(LoginRequiredMixin, TemplateView):
    """
    Shared base for Teacher / Room / Section timetable grid views.

    Subclasses must implement:
      - get_filter_queryset(timetable)  → filtered TimetableSlot queryset
      - get_selector_context()          → dict with selector dropdown data
      - filter_type                     → str ('teacher', 'room', or 'section')
      - filter_label                    → str (display name for current entity)

    Shared query params:
      - semester_id   → which semester's timetable versions to show
      - department_id → optional department scope for entity dropdowns
      - timetable_id  → version within the selected semester
      - teacher_id / room_id / section_id → entity within the current view
    """
    template_name = 'timetable/grid.html'
    filter_type = ''

    def get_selected_semester(self):
        return _get_selected_semester(self.request)

    def get_selected_department(self):
        return _get_selected_department(self.request)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        semester = self.get_selected_semester()
        department = self.get_selected_department()
        timetable, all_timetables = _get_timetable(self.request, semester)

        if not self.request.user.is_admin():
            all_timetables = all_timetables.filter(status=Timetable.Status.PUBLISHED)

        ctx['semester'] = semester
        ctx['selected_department'] = department
        ctx['all_semesters'] = _scoped_semesters(self.request)
        ctx['all_departments'] = _scoped_departments(self.request)
        ctx['timetable'] = timetable
        ctx['all_timetables'] = all_timetables
        ctx['filter_type'] = self.filter_type
        ctx['export_querystring'] = self.request.GET.urlencode()
        ctx['edit_lock_held_by_other'] = False
        ctx['edit_lock_holder'] = ''

        if timetable:
            if self.request.user.is_admin():
                ctx.update(_edit_lock_context(timetable, self.request.user))

            timeslots = list(
                TimeSlot.objects.filter(is_active=True)
                .order_by('day_of_week', 'period_number')
            )
            filtered_slots = list(self.get_filter_queryset(timetable))
            filtered_slots = _annotate_colour(filtered_slots)
            grid, days, periods = _build_grid(filtered_slots, timeslots)

            ctx['grid'] = grid
            ctx['days'] = days
            ctx['periods'] = periods
            ctx['slot_count'] = len(filtered_slots)
        else:
            ctx['grid'] = {}
            ctx['days'] = []
            ctx['periods'] = []
            ctx['slot_count'] = 0

        # Let subclass inject selector-specific context
        ctx.update(self.get_selector_context())

        return ctx

    def get_filter_queryset(self, timetable):
        raise NotImplementedError

    def get_selector_context(self):
        raise NotImplementedError


# ── Basic timetable placeholders ──────────────────────────────────────────

class GenerateTimetableView(RoleRequiredMixin, View):
    """Run the scheduling engine for the active semester and persist results."""
    allowed_roles = ['ADMIN']
    default_max_restarts = 10

    def get(self, request, *args, **kwargs):
        messages.info(request, "Use the Generate Timetable button on the dashboard.")
        return redirect('home')

    def post(self, request, *args, **kwargs):
        semester = _get_active_semester(self.request)
        if semester is None:
            messages.error(
                request,
                "No active semester is configured. Activate a semester before generating.",
            )
            return redirect('home')

        try:
            schedule_input = load_schedule_input(
                semester.id,
                school_id=_school_id_for_request(request),
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('home')

        try:
            max_restarts = int(request.POST.get('max_restarts', self.default_max_restarts))
        except (TypeError, ValueError):
            max_restarts = self.default_max_restarts

        result = run_scheduler(schedule_input, max_restarts=max_restarts)

        if not result.success:
            detail = result.failure_reason or "The scheduler could not find a hard-feasible timetable."
            if result.unplaced_activity_ids:
                detail = f"{detail} Unplaced class sessions: {len(result.unplaced_activity_ids)}."
            messages.error(request, detail)
            return redirect('home')

        try:
            with transaction.atomic():
                timetable = Timetable.objects.create(
                    semester=semester,
                    status=Timetable.Status.DRAFT,
                    penalty_score=result.penalty,
                )
                slot_dicts = placements_to_slot_dicts(
                    result,
                    schedule_input,
                    timetable_id=timetable.id,
                )
                TimetableSlot.objects.bulk_create([TimetableSlot(**d) for d in slot_dicts])
        except Exception as exc:
            messages.error(request, f"Timetable was generated but could not be saved: {exc}")
            return redirect('home')

        messages.success(
            request,
            (
                f"Timetable v{timetable.version} generated as a draft "
                f"(penalty score: {timetable.penalty_score}). "
                "Review the draft, then publish when ready."
            ),
        )
        return redirect('timetable:detail', pk=timetable.pk)


class TimetableListView(RoleRequiredMixin, ListView):
    """Admin-only list endpoint for timetable versions."""
    allowed_roles = ['ADMIN']
    model = Timetable
    template_name = 'timetable/list.html'
    context_object_name = 'timetables'

    def get_queryset(self):
        return _scoped_timetables(self.request).select_related('semester').order_by('-semester', '-version')


class TimetableDetailView(RoleRequiredMixin, DetailView):
    """Admin-only detail endpoint for a timetable version."""
    allowed_roles = ['ADMIN']
    model = Timetable
    template_name = 'timetable/detail.html'
    context_object_name = 'timetable'

    def get_queryset(self):
        return _scoped_timetables(self.request).select_related('semester', 'published_by')


class PublishTimetableView(RoleRequiredMixin, View):
    """Publish a draft timetable as the official schedule for its semester."""
    allowed_roles = ['ADMIN']

    def post(self, request, pk, *args, **kwargs):
        timetable = get_object_or_404(_scoped_timetables(request), pk=pk)

        if timetable.status != Timetable.Status.DRAFT:
            messages.error(request, "Only draft timetables can be published.")
            return redirect('timetable:detail', pk=pk)

        with transaction.atomic():
            Timetable.objects.filter(
                semester=timetable.semester,
                status=Timetable.Status.PUBLISHED,
            ).update(status=Timetable.Status.ARCHIVED)

            timetable.status = Timetable.Status.PUBLISHED
            timetable.published_at = timezone.now()
            timetable.published_by = request.user
            timetable.save(update_fields=['status', 'published_at', 'published_by'])

        messages.success(
            request,
            f"Timetable v{timetable.version} is now the official published schedule.",
        )
        return redirect('timetable:detail', pk=pk)


class DiscardDraftTimetableView(RoleRequiredMixin, View):
    """
    Discard a draft timetable version by marking it ARCHIVED.

    Slots are retained for audit history rather than deleted.
    """
    allowed_roles = ['ADMIN']

    def post(self, request, pk, *args, **kwargs):
        timetable = get_object_or_404(_scoped_timetables(request), pk=pk)

        if timetable.status != Timetable.Status.DRAFT:
            messages.error(request, "Only draft timetables can be discarded.")
            return redirect('timetable:detail', pk=pk)

        timetable.status = Timetable.Status.ARCHIVED
        timetable.save(update_fields=['status'])

        messages.success(
            request,
            f"Draft timetable v{timetable.version} has been archived.",
        )
        return redirect('timetable:list')


class TimetableDeleteView(RoleRequiredMixin, ProtectedDeleteMixin, DeleteView):
    """Permanently delete a draft or archived timetable version.

    Deletion cascades to this version's slots, staged change sets, and edit
    lock (all declared on_delete=CASCADE), so it is self-contained and safe.
    A PUBLISHED timetable is the live schedule and cannot be deleted directly;
    it must be discarded/replaced first. Queryset is tenant-scoped so an admin
    can only delete timetables belonging to their own school.
    """
    allowed_roles = ['ADMIN']
    model = Timetable
    template_name = 'timetable/timetable_confirm_delete.html'
    context_object_name = 'timetable'
    success_url = reverse_lazy('timetable:list')

    def get_queryset(self):
        return _scoped_timetables(self.request).select_related('semester')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.status == Timetable.Status.PUBLISHED:
            messages.error(
                request,
                "This timetable is published (the live schedule) and cannot be "
                "deleted. Publish another version or discard it first.",
            )
            return redirect('timetable:list')
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        self.success_message = (
            f"Timetable v{self.object.version} for "
            f"{self.object.semester.name} was deleted."
        )
        return super().form_valid(form)


# ── My Routine (mobile-first viewer) ─────────────────────────────────────

class MyRoutineView(RoleRequiredMixin, TemplateView):
    """
    Mobile-first personal routine for teachers and class reps.

    Uses only PUBLISHED timetables for the active semester.
    """
    allowed_roles = ['TEACHER', 'CLASS_REP']
    template_name = 'timetable/my_routine.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        now = _local_now()

        semester = _get_active_semester(self.request)
        timetable, _all_timetables = _get_timetable(self.request, semester)

        ctx['semester'] = semester
        ctx['timetable'] = timetable
        ctx['now'] = now
        ctx['routine_role'] = user.role
        ctx['next_slot'] = None
        ctx['next_slot_countdown'] = ''
        ctx['today_slots'] = []
        ctx['week_grid'] = {}
        ctx['days'] = []
        ctx['periods'] = []
        ctx['section'] = None
        ctx['slot_count'] = 0

        if not semester or not timetable:
            return ctx

        filtered_qs = self._get_routine_slots(timetable)
        filtered_slots = _annotate_colour(list(filtered_qs))
        ctx['slot_count'] = len(filtered_slots)

        if not filtered_slots:
            return ctx

        timeslots = list(
            TimeSlot.objects.filter(is_active=True)
            .order_by('day_of_week', 'period_number')
        )
        grid, days, periods = _build_grid(filtered_slots, timeslots)

        next_slot, countdown = _resolve_next_slot(filtered_slots, now=now)

        ctx['next_slot'] = next_slot
        ctx['next_slot_countdown'] = countdown
        ctx['today_slots'] = _today_slots(filtered_slots, now=now)
        ctx['week_grid'] = grid
        ctx['days'] = days
        ctx['periods'] = periods

        if user.is_class_rep():
            profile = getattr(user, 'class_rep_profile', None)
            if profile and profile.is_active:
                ctx['section'] = profile.section

        return ctx

    def _get_routine_slots(self, timetable):
        user = self.request.user
        base_qs = _get_base_slot_queryset(timetable)

        if user.is_teacher():
            teacher = getattr(user, 'teacher_profile', None)
            if teacher is None:
                return TimetableSlot.objects.none()
            return base_qs.filter(teacher=teacher)

        profile = getattr(user, 'class_rep_profile', None)
        if profile is None or not profile.is_active:
            return TimetableSlot.objects.none()
        return base_qs.filter(class_session__section=profile.section)


class TimetableDirectoryView(RoleRequiredMixin, TemplateView):
    """Lightweight hub linking to institution-wide timetable grids."""
    allowed_roles = ['TEACHER', 'CLASS_REP']
    template_name = 'timetable/directory.html'


# ── Teacher Timetable View ─────────────────────────────────────────────────

class TeacherTimetableView(BaseTimetableGridView):
    """
    Teacher timetable grid.

    - Teachers see their own schedule by default; any teacher may browse others
      via ?teacher_id=.
    - Admins see a dropdown to select any teacher.
    - Optional ?department_id= narrows the teacher list.
    """
    filter_type = 'teacher'

    def _teacher_queryset(self):
        return _teachers_for_filters(
            self.request,
            department=self.get_selected_department(),
        )

    def _get_selected_teacher(self):
        """Resolve the teacher whose timetable to display."""
        user = self.request.user
        qs = self._teacher_queryset()
        teacher_id = self.request.GET.get('teacher_id')

        if teacher_id:
            selected = qs.filter(pk=teacher_id).first()
            if selected:
                return selected

        if user.is_admin():
            return qs.first()

        profile = getattr(user, 'teacher_profile', None)
        if profile is None:
            return None
        department = self.get_selected_department()
        # Keep the signed-in teacher visible even when a department filter
        # would otherwise hide them from the dropdown.
        if department is None or profile.department_id == department.pk:
            return profile
        return qs.first()

    def get_filter_queryset(self, timetable):
        teacher = self._get_selected_teacher()
        if teacher is None:
            return TimetableSlot.objects.none()
        return _get_base_slot_queryset(timetable).filter(teacher=teacher)

    def get_selector_context(self):
        teacher = self._get_selected_teacher()
        return {
            'selected_teacher': teacher,
            'filter_label': str(teacher) if teacher else 'No teacher selected',
            'all_teachers': self._teacher_queryset(),
        }


# ── Room Timetable View ───────────────────────────────────────────────────

class RoomTimetableView(RoleRequiredMixin, BaseTimetableGridView):
    """Room timetable grid with room selector dropdown."""
    allowed_roles = ['ADMIN', 'TEACHER', 'CLASS_REP']
    filter_type = 'room'

    def _room_queryset(self):
        return _rooms_for_filters(
            self.request,
            department=self.get_selected_department(),
        )

    def _get_selected_room(self):
        qs = self._room_queryset()
        room_id = self.request.GET.get('room_id')
        if room_id:
            selected = qs.filter(pk=room_id).first()
            if selected:
                return selected
        return qs.first()

    def get_filter_queryset(self, timetable):
        room = self._get_selected_room()
        if room is None:
            return TimetableSlot.objects.none()
        return _get_base_slot_queryset(timetable).filter(room=room)

    def get_selector_context(self):
        room = self._get_selected_room()
        return {
            'selected_room': room,
            'filter_label': room.name if room else 'No room selected',
            'all_rooms': self._room_queryset(),
        }


# ── Section Timetable View ────────────────────────────────────────────────

class SectionTimetableView(RoleRequiredMixin, BaseTimetableGridView):
    """Section timetable grid with section selector dropdown."""
    allowed_roles = ['ADMIN', 'TEACHER', 'CLASS_REP']
    filter_type = 'section'

    def _section_queryset(self):
        return _sections_for_filters(
            self.request,
            semester=self.get_selected_semester(),
            department=self.get_selected_department(),
        )

    def _get_selected_section(self):
        qs = self._section_queryset()
        section_id = self.request.GET.get('section_id')
        if section_id:
            selected = qs.filter(pk=section_id).first()
            if selected:
                return selected
        if self.request.user.is_class_rep():
            profile = getattr(self.request.user, 'class_rep_profile', None)
            if profile and profile.is_active:
                owned = qs.filter(pk=profile.section_id).first()
                if owned:
                    return owned
        return qs.first()

    def get_filter_queryset(self, timetable):
        section = self._get_selected_section()
        if section is None:
            return TimetableSlot.objects.none()
        return _get_base_slot_queryset(timetable).filter(
            class_session__section=section
        )

    def get_selector_context(self):
        section = self._get_selected_section()
        return {
            'selected_section': section,
            'filter_label': section.name if section else 'No section selected',
            'all_sections': self._section_queryset(),
        }


# ── Drag-and-Drop Editor Endpoints ────────────────────────────────────────

class MoveSlotView(RoleRequiredMixin, View):
    """Admin-only JSON endpoint that validates and applies one slot move.

    Deprecated after batch editor (Prompt 06B) — use validate_batch + publish_change_set.
    """
    allowed_roles = ['ADMIN']

    def post(self, request, *args, **kwargs):
        payload = _json_body(request)
        if payload is None:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON body.'}, status=400)

        slot_id = payload.get('slot_id')
        target_day = payload.get('target_day')
        target_period = payload.get('target_period')
        target_room = payload.get('target_room')

        if not all([slot_id, target_day, target_period, target_room]):
            return JsonResponse({
                'ok': False,
                'error': 'Move request must include slot_id, target_day, target_period, and target_room.',
            }, status=400)

        try:
            slot_id = int(slot_id)
            target_day = int(target_day)
            target_period = int(target_period)
            target_room = int(target_room)
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': 'Move target values must be numeric.'}, status=400)

        try:
            target_timeslot = TimeSlot.objects.get(
                day_of_week=target_day,
                period_number=target_period,
                is_active=True,
            )
        except TimeSlot.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Target period is not active.'}, status=400)

        slot = get_object_or_404(
            _scoped_timetable_slots(request).select_related(
                'timetable', 'class_session', 'teacher', 'room', 'timeslot'
            ),
            pk=slot_id,
        )
        timetable = slot.timetable

        if not _scoped_rooms(request).filter(pk=target_room).exists():
            return JsonResponse({'ok': False, 'error': 'Target room is not available.'}, status=400)

        schedule_input = load_schedule_input(
            timetable.semester_id,
            school_id=_school_id_for_request(request),
        )
        activity = schedule_input.activities_by_id.get(slot.class_session_id)
        if activity is None:
            return JsonResponse({
                'ok': False,
                'error': 'This class session is not part of the timetable semester.',
            }, status=400)

        existing_slots = list(
            TimetableSlot.objects
            .filter(timetable=timetable)
            .exclude(pk=slot.pk)
            .select_related('class_session', 'timeslot', 'room')
        )
        existing_placements = _slots_to_placements(existing_slots)
        validation = validate_single_placement(
            activity,
            target_timeslot.id,
            target_room,
            existing_placements,
            schedule_input,
        )
        if not validation.is_valid:
            return JsonResponse({
                'ok': False,
                'error': validation.message,
                'resource_type': validation.resource_type,
                'resource_id': validation.resource_id,
            }, status=409)

        try:
            with transaction.atomic():
                slot.timeslot = target_timeslot
                slot.room_id = target_room
                slot.teacher_id = slot.class_session.teacher_id
                slot.is_locked = True
                slot.is_manual = True
                slot.save(update_fields=['timeslot', 'room', 'teacher', 'is_locked', 'is_manual'])

                updated_slots = list(TimetableSlot.objects.filter(timetable=timetable))
                penalty = compute_penalty(_slots_to_placements(updated_slots), schedule_input)
                timetable.penalty_score = penalty
                timetable.save(update_fields=['penalty_score'])
        except (IntegrityError, ValueError):
            return JsonResponse({
                'ok': False,
                'error': 'The database rejected this move because it conflicts with an existing placement.',
            }, status=409)

        return JsonResponse({
            'ok': True,
            'slot_id': slot.pk,
            'target_day': target_timeslot.day_of_week,
            'target_period': target_timeslot.period_number,
            'target_room': slot.room_id,
            'is_locked': slot.is_locked,
            'is_manual': slot.is_manual,
            'penalty_score': timetable.penalty_score,
        })


class UnlockSlotView(RoleRequiredMixin, View):
    """Admin-only JSON endpoint that releases one manual placement."""
    allowed_roles = ['ADMIN']

    def post(self, request, *args, **kwargs):
        payload = _json_body(request)
        if payload is None:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON body.'}, status=400)

        slot_id = payload.get('slot_id')
        if not slot_id:
            return JsonResponse({'ok': False, 'error': 'slot_id is required.'}, status=400)

        slot = get_object_or_404(_scoped_timetable_slots(request), pk=slot_id)
        slot.is_locked = False
        slot.is_manual = False
        slot.save(update_fields=['is_locked', 'is_manual'])
        return JsonResponse({'ok': True, 'slot_id': slot.pk, 'is_locked': False, 'is_manual': False})


class ValidateBatchView(RoleRequiredMixin, View):
    """Admin-only JSON endpoint that validates a batch of staged slot moves."""
    allowed_roles = ['ADMIN']

    def post(self, request, *args, **kwargs):
        payload = _json_body(request)
        if payload is None:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON body.'}, status=400)

        timetable_id = payload.get('timetable_id')
        moves_raw = payload.get('moves')
        if timetable_id is None:
            return JsonResponse({'ok': False, 'error': 'timetable_id is required.'}, status=400)
        if moves_raw is None:
            return JsonResponse({'ok': False, 'error': 'moves is required.'}, status=400)

        try:
            timetable_id = int(timetable_id)
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': 'timetable_id must be numeric.'}, status=400)

        timetable = get_object_or_404(_scoped_timetables(request), pk=timetable_id)

        acquired, lock = acquire_lock(timetable, request.user)
        if not acquired:
            return _edit_lock_denied_response(lock)

        try:
            move_payloads = parse_move_payloads(moves_raw)
        except MoveParseError as exc:
            return JsonResponse({'ok': False, 'error': exc.message}, status=exc.status)

        try:
            schedule_input = load_schedule_input(
                timetable.semester_id,
                school_id=_school_id_for_request(request),
            )
        except ValueError as exc:
            return JsonResponse({'ok': False, 'error': str(exc)}, status=400)

        placements = build_hypothetical_placements(timetable, move_payloads)
        violations = find_hard_violations(placements, schedule_input)
        penalty = compute_penalty(placements, schedule_input)
        is_valid = len(violations) == 0

        with transaction.atomic():
            change_set = DraftChangeSet.objects.filter(
                timetable=timetable,
                created_by=request.user,
                is_published=False,
                is_discarded=False,
            ).first()
            if change_set is None:
                change_set = DraftChangeSet.objects.create(
                    timetable=timetable,
                    created_by=request.user,
                )
            else:
                change_set.moves.all().delete()

            if move_payloads:
                slot_map = {
                    slot.pk: slot
                    for slot in TimetableSlot.objects.filter(
                        timetable=timetable,
                        pk__in=[move['slot_id'] for move in move_payloads],
                    )
                }
                DraftMove.objects.bulk_create([
                    DraftMove(
                        change_set=change_set,
                        slot=slot_map[move['slot_id']],
                        target_timeslot=move['target_timeslot'],
                        target_room_id=move['target_room_id'],
                    )
                    for move in move_payloads
                ])

            change_set.is_valid = is_valid
            change_set.last_checked_at = timezone.now()
            change_set.save(update_fields=['is_valid', 'last_checked_at'])

        return JsonResponse({
            'ok': True,
            'is_valid': is_valid,
            'violations': violations,
            'penalty_score': penalty,
            'change_set_id': change_set.pk,
        })


class PublishChangeSetView(RoleRequiredMixin, View):
    """Admin-only JSON endpoint that commits a validated draft change set."""
    allowed_roles = ['ADMIN']

    def post(self, request, *args, **kwargs):
        payload = _json_body(request)
        if payload is None:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON body.'}, status=400)

        change_set_id = payload.get('change_set_id')
        if not change_set_id:
            return JsonResponse({'ok': False, 'error': 'change_set_id is required.'}, status=400)

        change_set = get_object_or_404(
            _scoped_draft_change_sets(request).select_related('timetable'),
            pk=change_set_id,
        )

        if change_set.is_published or change_set.is_discarded:
            return JsonResponse({'ok': False, 'error': 'Change set is no longer active.'}, status=400)
        if not change_set.is_valid:
            return JsonResponse({
                'ok': False,
                'error': 'Change set must be validated before publish.',
            }, status=400)

        timetable = change_set.timetable
        acquired, lock = acquire_lock(timetable, request.user)
        if not acquired:
            return _edit_lock_denied_response(lock)

        draft_moves = list(
            change_set.moves.select_related('slot__class_session', 'target_timeslot', 'target_room')
        )
        published_move_count = len(draft_moves)

        try:
            with transaction.atomic():
                for draft_move in draft_moves:
                    slot = draft_move.slot
                    slot.timeslot = draft_move.target_timeslot
                    slot.room = draft_move.target_room
                    slot.teacher_id = slot.class_session.teacher_id
                    slot.is_locked = True
                    slot.is_manual = True
                    slot.save(update_fields=['timeslot', 'room', 'teacher', 'is_locked', 'is_manual'])

                schedule_input = load_schedule_input(
                    timetable.semester_id,
                    school_id=_school_id_for_request(request),
                )
                updated_slots = list(TimetableSlot.objects.filter(timetable=timetable))
                penalty = compute_penalty(_slots_to_placements(updated_slots), schedule_input)
                timetable.penalty_score = penalty
                timetable.save(update_fields=['penalty_score'])

                change_set.is_published = True
                change_set.save(update_fields=['is_published'])
                change_set.moves.all().delete()
        except IntegrityError:
            return JsonResponse({
                'ok': False,
                'error': 'The database rejected this publish because it conflicts with an existing placement.',
            }, status=409)

        release_lock(timetable)

        return JsonResponse({
            'ok': True,
            'change_set_id': change_set.pk,
            'penalty_score': timetable.penalty_score,
            'published_move_count': published_move_count,
        })


class DiscardChangeSetView(RoleRequiredMixin, View):
    """Admin-only JSON endpoint that discards a draft change set without applying moves."""
    allowed_roles = ['ADMIN']

    def post(self, request, *args, **kwargs):
        payload = _json_body(request)
        if payload is None:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON body.'}, status=400)

        change_set_id = payload.get('change_set_id')
        if not change_set_id:
            return JsonResponse({'ok': False, 'error': 'change_set_id is required.'}, status=400)

        change_set = get_object_or_404(_scoped_draft_change_sets(request), pk=change_set_id)

        if change_set.is_published:
            return JsonResponse({'ok': False, 'error': 'Published change sets cannot be discarded.'}, status=400)
        if change_set.is_discarded:
            return JsonResponse({'ok': True, 'change_set_id': change_set.pk, 'discarded': True})

        timetable = change_set.timetable
        acquired, lock = acquire_lock(timetable, request.user)
        if not acquired:
            return _edit_lock_denied_response(lock)

        change_set.is_discarded = True
        change_set.is_valid = False
        change_set.save(update_fields=['is_discarded', 'is_valid'])
        change_set.moves.all().delete()
        release_lock(timetable)

        return JsonResponse({
            'ok': True,
            'change_set_id': change_set.pk,
            'discarded': True,
        })


# ── Export Views ──────────────────────────────────────────────────────────

def _active_timeslots():
    return list(TimeSlot.objects.filter(is_active=True).order_by('day_of_week', 'period_number'))


def _redirect_name_for_scope(scope):
    return {
        'teacher': 'timetable:teacher_view',
        'room': 'timetable:room_view',
        'section': 'timetable:section_view',
        'full': 'timetable:reports',
    }.get(scope, 'timetable:teacher_view')


class ExportTimetableView(LoginRequiredMixin, View):
    """Download a filtered timetable as PDF or XLSX."""
    valid_scopes = {'teacher', 'room', 'section', 'full'}
    valid_formats = {'pdf', 'xlsx'}

    def get(self, request, scope, file_format, *args, **kwargs):
        if scope not in self.valid_scopes or file_format not in self.valid_formats:
            raise PermissionDenied

        if scope == 'full' and not request.user.is_admin():
            raise PermissionDenied

        semester = _get_selected_semester(request)
        timetable, _all_timetables = _get_timetable(request, semester)
        if not semester or not timetable:
            messages.warning(request, "Generate a timetable before exporting.")
            return redirect(_redirect_name_for_scope(scope))

        slots, title, label = self._resolve_slots(request, timetable, scope)
        timeslots = _active_timeslots()
        subtitle = f"{timetable.semester.name} - v{timetable.version} ({timetable.get_status_display()})"
        if label:
            subtitle = f"{subtitle} - {label}"

        department = _get_selected_department(request)
        if department is not None:
            subtitle = f"{subtitle} - {department.name}"

        if file_format == 'pdf':
            content = export_timetable_pdf(
                slots=slots,
                timeslots=timeslots,
                title=title,
                subtitle=subtitle,
                scope=scope,
            )
            content_type = 'application/pdf'
            extension = 'pdf'
        else:
            content = export_timetable_xlsx(
                slots=slots,
                timeslots=timeslots,
                title=title,
                subtitle=subtitle,
                scope=scope,
            )
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            extension = 'xlsx'

        filename = f"{slugify(title)}-v{timetable.version}.{extension}"
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def _resolve_slots(self, request, timetable, scope):
        base_qs = _get_base_slot_queryset(timetable)

        if scope == 'teacher':
            teacher = self._selected_teacher(request)
            if teacher is None:
                return [], "Teacher Timetable", "No teacher selected"
            return (
                list(base_qs.filter(teacher=teacher)),
                "Teacher Timetable",
                str(teacher),
            )

        if scope == 'room':
            room = self._selected_room(request)
            if room is None:
                return [], "Room Timetable", "No room selected"
            return (
                list(base_qs.filter(room=room)),
                "Room Timetable",
                room.name,
            )

        if scope == 'section':
            section = self._selected_section(request, timetable.semester)
            if section is None:
                return [], "Section Timetable", "No section selected"
            return (
                list(base_qs.filter(class_session__section=section)),
                "Section Timetable",
                section.name,
            )

        return list(base_qs), "Full Institution Timetable", "All teachers, rooms, and sections"

    def _selected_teacher(self, request):
        department = _get_selected_department(request)
        qs = _teachers_for_filters(request, department=department)
        profile = getattr(request.user, 'teacher_profile', None)

        # Teachers may only export their own timetable — ignore foreign teacher_id.
        if request.user.is_teacher() and not request.user.is_admin():
            return profile

        teacher_id = request.GET.get('teacher_id')
        if teacher_id:
            selected = qs.filter(pk=teacher_id).first()
            if selected:
                return selected
        if request.user.is_admin():
            return qs.first()
        if profile is None:
            return None
        if department is None or profile.department_id == department.pk:
            return profile
        return qs.first()

    def _selected_room(self, request):
        department = _get_selected_department(request)
        qs = _rooms_for_filters(request, department=department)
        room_id = request.GET.get('room_id')
        if room_id:
            selected = qs.filter(pk=room_id).first()
            if selected:
                return selected
        return qs.first()

    def _selected_section(self, request, semester):
        department = _get_selected_department(request)
        qs = _sections_for_filters(request, semester=semester, department=department)
        section_id = request.GET.get('section_id')
        if section_id:
            selected = qs.filter(pk=section_id).first()
            if selected:
                return selected
        if request.user.is_class_rep():
            profile = getattr(request.user, 'class_rep_profile', None)
            if profile and profile.is_active:
                owned = qs.filter(pk=profile.section_id).first()
                if owned:
                    return owned
        return qs.first()


# ── Reports View ──────────────────────────────────────────────────────────

class ReportsView(RoleRequiredMixin, TemplateView):
    """Admin-only printable operational timetable reports."""
    allowed_roles = ['ADMIN']
    template_name = 'timetable/reports.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        semester = _get_active_semester(self.request)
        timetable, all_timetables = _get_timetable(self.request, semester)

        ctx['semester'] = semester
        ctx['timetable'] = timetable
        ctx['all_timetables'] = all_timetables
        ctx['export_querystring'] = self.request.GET.urlencode()

        if not timetable:
            ctx.update({
                'teacher_workloads': [],
                'room_utilization': [],
                'soft_penalties': [],
                'total_penalty': 0,
            })
            return ctx

        slots = list(_get_base_slot_queryset(timetable))
        timeslot_count = TimeSlot.objects.filter(is_active=True).count()
        teacher_workloads = self._teacher_workloads(slots)
        room_utilization = self._room_utilization(slots, timeslot_count)
        soft_penalties, total_penalty = _soft_penalty_rows(timetable, semester, slots)

        ctx['teacher_workloads'] = teacher_workloads
        ctx['room_utilization'] = room_utilization
        ctx['soft_penalties'] = soft_penalties
        ctx['total_penalty'] = total_penalty

        # Constraint-satisfaction summary. Hard constraints are guaranteed by the
        # engine (a timetable only exists if they are all satisfied); soft rules
        # may carry penalties.
        from django.db.models import Q
        from scheduling.models import Constraint

        active_constraints = Constraint.objects.filter(is_active=True).filter(
            Q(semester=semester) | Q(semester__isnull=True)
        )
        hard_count = active_constraints.filter(is_hard=True).count()
        soft_count = active_constraints.filter(is_hard=False).count()
        violated_soft = len(soft_penalties)
        satisfied_soft = max(soft_count - violated_soft, 0)
        total_rules = hard_count + soft_count
        satisfied_rules = hard_count + satisfied_soft
        ctx['constraint_summary'] = {
            'hard_count': hard_count,
            'soft_count': soft_count,
            'violated_soft': violated_soft,
            'satisfied_soft': satisfied_soft,
            'total_rules': total_rules,
            'satisfied_rules': satisfied_rules,
            'satisfaction_rate': round(satisfied_rules / total_rules * 100) if total_rules else 100,
        }
        return ctx

    def _teacher_workloads(self, slots):
        rows = {}
        for slot in slots:
            if not slot.teacher:
                continue
            row = rows.setdefault(slot.teacher_id, {
                'teacher': slot.teacher,
                'periods': 0,
                'sections': set(),
                'subjects': set(),
            })
            row['periods'] += 1
            row['sections'].add(slot.class_session.section.name)
            row['subjects'].add(slot.class_session.subject.code)

        return sorted(rows.values(), key=lambda row: row['periods'], reverse=True)

    def _room_utilization(self, slots, timeslot_count):
        rows = {}
        for room in _scoped_rooms(self.request).order_by('name'):
            rows[room.pk] = {
                'room': room,
                'used_periods': 0,
                'utilization': 0,
            }

        for slot in slots:
            if slot.room_id in rows:
                rows[slot.room_id]['used_periods'] += 1

        denominator = max(timeslot_count, 1)
        for row in rows.values():
            row['utilization'] = round((row['used_periods'] / denominator) * 100, 1)
        return sorted(rows.values(), key=lambda row: row['utilization'], reverse=True)


def _soft_penalty_rows(timetable, semester, slots=None):
    if not timetable or not semester:
        return [], 0

    if slots is None:
        slots = list(_get_base_slot_queryset(timetable))

    teacher_day_periods = defaultdict(list)
    teacher_day_counts = defaultdict(int)
    teacher_names = {}

    for slot in slots:
        if slot.teacher_id is None:
            continue
        key = (slot.teacher_id, slot.timeslot.day_of_week)
        teacher_day_periods[key].append(slot.timeslot.period_number)
        teacher_day_counts[key] += 1
        teacher_names[slot.teacher_id] = (
            slot.teacher.user.get_full_name()
            if slot.teacher and slot.teacher.user
            else f"Teacher #{slot.teacher_id}"
        )

    for periods in teacher_day_periods.values():
        periods.sort()

    soft_constraints = list(
        Constraint.objects.filter(
            semester=semester,
            is_active=True,
            is_hard=False,
        ).select_related('teacher')
    )

    day_names = {
        1: 'Monday', 2: 'Tuesday', 3: 'Wednesday',
        4: 'Thursday', 5: 'Friday',
    }
    violations = []
    total_penalty = 0

    for constraint in soft_constraints:
        teacher_ids = (
            [constraint.teacher_id]
            if constraint.teacher_id is not None
            else list(teacher_names.keys())
        )

        if constraint.constraint_type == 'MAX_DAILY_HOURS' and constraint.max_daily_periods is not None:
            for teacher_id in teacher_ids:
                for day in range(1, 6):
                    count = teacher_day_counts.get((teacher_id, day), 0)
                    excess = max(0, count - constraint.max_daily_periods)
                    if excess:
                        penalty = excess * constraint.weight
                        total_penalty += penalty
                        violations.append({
                            'type': 'Max Daily Hours',
                            'type_icon': 'bi-clock-history',
                            'teacher': teacher_names.get(teacher_id, f'Teacher #{teacher_id}'),
                            'teacher_id': teacher_id,
                            'day': day_names.get(day, f'Day {day}'),
                            'detail': f'{count} periods scheduled, soft limit is {constraint.max_daily_periods}',
                            'excess': excess,
                            'penalty': penalty,
                            'weight': constraint.weight,
                        })

        elif constraint.constraint_type == 'NO_ADJACENT_GAPS':
            for teacher_id in teacher_ids:
                for day in range(1, 6):
                    periods = teacher_day_periods.get((teacher_id, day), [])
                    gaps = 0
                    for index in range(1, len(periods)):
                        if periods[index] - periods[index - 1] > 1:
                            gaps += 1
                    if gaps:
                        penalty = gaps * constraint.weight
                        total_penalty += penalty
                        violations.append({
                            'type': 'Schedule Gap',
                            'type_icon': 'bi-exclamation-triangle',
                            'teacher': teacher_names.get(teacher_id, f'Teacher #{teacher_id}'),
                            'teacher_id': teacher_id,
                            'day': day_names.get(day, f'Day {day}'),
                            'detail': f'{gaps} gap(s) in periods {periods}',
                            'excess': gaps,
                            'penalty': penalty,
                            'weight': constraint.weight,
                        })

    violations.sort(key=lambda row: row['penalty'], reverse=True)
    return violations, total_penalty


# ── Conflict Report View ──────────────────────────────────────────────────

class ConflictReportView(RoleRequiredMixin, TemplateView):
    """
    Admin-only view that surfaces soft-constraint violations as actionable
    information — not just the penalty number from the engine, but a
    per-teacher, per-day breakdown of what's causing penalties.

    Recomputes from stored TimetableSlot data + active Constraint records
    so the report always reflects the current constraint configuration.
    """
    allowed_roles = ['ADMIN']
    template_name = 'timetable/conflict_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        semester = _get_active_semester(self.request)
        timetable, all_timetables = _get_timetable(self.request, semester)

        ctx['semester'] = semester
        ctx['timetable'] = timetable
        ctx['all_timetables'] = all_timetables

        if not timetable:
            ctx['violations'] = []
            ctx['total_penalty'] = 0
            ctx['stored_penalty'] = 0
            return ctx

        ctx['stored_penalty'] = timetable.penalty_score

        # ── Load slots with full joins ──
        slots = list(
            _get_base_slot_queryset(timetable)
        )

        # ── Build per-teacher, per-day aggregates ──
        DAY_NAMES = {
            1: 'Monday', 2: 'Tuesday', 3: 'Wednesday',
            4: 'Thursday', 5: 'Friday',
        }

        # teacher_day_periods: (teacher_id, day) → sorted list of period numbers
        teacher_day_periods = defaultdict(list)
        # teacher_day_counts: (teacher_id, day) → count
        teacher_day_counts = defaultdict(int)
        # teacher names for display
        teacher_names = {}

        for slot in slots:
            if slot.teacher_id is None:
                continue
            day = slot.timeslot.day_of_week
            period = slot.timeslot.period_number
            key = (slot.teacher_id, day)
            teacher_day_periods[key].append(period)
            teacher_day_counts[key] += 1
            if slot.teacher_id not in teacher_names:
                teacher_names[slot.teacher_id] = (
                    slot.teacher.user.get_full_name()
                    if slot.teacher and slot.teacher.user
                    else f'Teacher #{slot.teacher_id}'
                )

        # Sort period lists for gap detection
        for key in teacher_day_periods:
            teacher_day_periods[key].sort()

        # ── Evaluate soft constraints ──
        if semester:
            soft_constraints = list(
                Constraint.objects.filter(
                    semester=semester,
                    is_active=True,
                    is_hard=False,
                ).select_related('teacher')
            )
        else:
            soft_constraints = []

        violations = []
        total_penalty = 0

        for c in soft_constraints:
            if c.constraint_type == 'MAX_DAILY_HOURS' and c.max_daily_periods is not None:
                # Check per-teacher daily hour overages
                if c.teacher_id is not None:
                    # Teacher-specific constraint
                    teacher_ids = [c.teacher_id]
                else:
                    # Global: applies to all teachers
                    teacher_ids = list(teacher_names.keys())

                for tid in teacher_ids:
                    for day in range(1, 6):
                        count = teacher_day_counts.get((tid, day), 0)
                        excess = max(0, count - c.max_daily_periods)
                        if excess > 0:
                            penalty = excess * c.weight
                            total_penalty += penalty
                            violations.append({
                                'type': 'Max Daily Hours',
                                'type_icon': 'bi-clock-history',
                                'teacher': teacher_names.get(tid, f'Teacher #{tid}'),
                                'teacher_id': tid,
                                'day': DAY_NAMES.get(day, f'Day {day}'),
                                'detail': (
                                    f'{count} periods scheduled, '
                                    f'soft limit is {c.max_daily_periods}'
                                ),
                                'excess': excess,
                                'penalty': penalty,
                                'weight': c.weight,
                            })

            elif c.constraint_type == 'NO_ADJACENT_GAPS':
                # Check per-teacher schedule gaps
                if c.teacher_id is not None:
                    teacher_ids = [c.teacher_id]
                else:
                    teacher_ids = list(teacher_names.keys())

                for tid in teacher_ids:
                    for day in range(1, 6):
                        periods = teacher_day_periods.get((tid, day), [])
                        if len(periods) <= 1:
                            continue
                        gaps = 0
                        for i in range(1, len(periods)):
                            if periods[i] - periods[i - 1] > 1:
                                gaps += 1
                        if gaps > 0:
                            penalty = gaps * c.weight
                            total_penalty += penalty
                            violations.append({
                                'type': 'Schedule Gap',
                                'type_icon': 'bi-exclamation-triangle',
                                'teacher': teacher_names.get(tid, f'Teacher #{tid}'),
                                'teacher_id': tid,
                                'day': DAY_NAMES.get(day, f'Day {day}'),
                                'detail': (
                                    f'{gaps} gap(s) in periods {periods}'
                                ),
                                'excess': gaps,
                                'penalty': penalty,
                                'weight': c.weight,
                            })

        # Sort violations by penalty descending for visibility
        violations.sort(key=lambda v: v['penalty'], reverse=True)

        ctx['violations'] = violations
        ctx['total_penalty'] = total_penalty
        ctx['violation_count'] = len(violations)

        # Penalty severity classification
        if total_penalty == 0:
            ctx['penalty_level'] = 'none'
        elif total_penalty <= 50:
            ctx['penalty_level'] = 'low'
        else:
            ctx['penalty_level'] = 'high'

        return ctx
