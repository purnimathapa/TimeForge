"""
scheduling/engine/models_io.py

ORM adapter — the ONLY file in scheduling/engine/ that may import Django models.

Responsibilities:
  1. load_schedule_input(semester_id)  → ScheduleInput
     Reads ClassSession, TimeSlot, TeacherAvailability, Constraint, Room
     rows for the given semester and converts them into the engine's internal
     dataclasses.  The result is a fully self-contained ScheduleInput that
     can be passed to run_scheduler() without any further DB access.

  2. placements_to_slot_dicts(result, schedule_input)  → list[dict]
     Converts the engine's Placement objects back into field-value dicts
     matching the TimetableSlot model schema (to be defined in Prompt 11).
     Does NOT save anything to the database.

Design contract:
  - algorithm.py, constraints.py, and data_types.py must NEVER import from
    this file.  The dependency direction is:
        models_io  →  data_types  (only)
        algorithm  →  constraints, data_types
  - All DB access in this file must use .select_related() to minimise queries.
"""

from __future__ import annotations

import logging
from typing import Optional

from .data_types import (
    ActivityData,
    ConstraintData,
    RoomData,
    ScheduleInput,
    ScheduleResult,
    SectionData,
    TeacherData,
    TimeSlotData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public: ORM → ScheduleInput
# ---------------------------------------------------------------------------

def load_schedule_input(semester_id: int) -> ScheduleInput:
    """
    Load all data needed by the engine for a given semester and return a
    ScheduleInput populated with pure-Python dataclasses.

    Raises
    ------
    ValueError
        If the semester does not exist or has no active timeslots.

    Usage
    -----
    >>> from scheduling.engine.models_io import load_schedule_input
    >>> from scheduling.engine.algorithm import run_scheduler
    >>> schedule_input = load_schedule_input(semester_id=1)
    >>> result = run_scheduler(schedule_input)
    """
    # Import Django models here (and only here) so that the rest of the engine
    # package is importable without a configured Django application.
    from core.models import Room, Semester
    from academics.models import ClassSession, TeacherProfile
    from scheduling.models import Constraint, TeacherAvailability, TimeSlot

    # ---- Validate semester exists ----
    try:
        semester = Semester.objects.get(pk=semester_id)
    except Semester.DoesNotExist:
        raise ValueError(f"Semester with id={semester_id} does not exist.")

    logger.info("Loading schedule input for semester %r (id=%d)", semester.name, semester_id)

    # ---- TimeSlots ----
    db_slots = TimeSlot.objects.filter(is_active=True).order_by("day_of_week", "period_number")
    if not db_slots.exists():
        raise ValueError("No active TimeSlot records found. Create timeslots before scheduling.")

    timeslots = [
        TimeSlotData(
            id=ts.id,
            day_of_week=ts.day_of_week,
            period_number=ts.period_number,
            start_time=ts.start_time.strftime("%H:%M"),
            end_time=ts.end_time.strftime("%H:%M"),
        )
        for ts in db_slots
    ]

    # ---- Rooms ----
    db_rooms = Room.objects.filter(is_active=True)
    rooms = [
        RoomData(
            id=r.id,
            name=r.name,
            capacity=r.capacity,
            room_type=r.room_type,
        )
        for r in db_rooms
    ]

    # ---- Teachers + their unavailability ----
    # Load all teachers who have at least one ClassSession in this semester.
    # We determine semester membership via ClassSession → section → semester.
    semester_sessions = ClassSession.objects.filter(
        section__semester_id=semester_id,
    ).select_related("teacher", "section", "subject")

    teacher_ids_in_semester = set(
        s.teacher_id for s in semester_sessions if s.teacher_id is not None
    )

    # Build unavailability map: teacher_id → frozenset of unavailable timeslot ids
    unavailability: dict[int, set[int]] = {tid: set() for tid in teacher_ids_in_semester}
    db_avail = TeacherAvailability.objects.filter(
        teacher_id__in=teacher_ids_in_semester,
        is_available=False,
    ).select_related("timeslot")
    for row in db_avail:
        unavailability.setdefault(row.teacher_id, set()).add(row.timeslot_id)

    db_teachers = TeacherProfile.objects.filter(
        pk__in=teacher_ids_in_semester,
        is_active=True,
    ).select_related("user")

    teachers = [
        TeacherData(
            id=t.id,
            name=t.user.get_full_name() or t.user.username,
            max_hours_per_day=t.max_hours_per_day,
            unavailable_slot_ids=frozenset(unavailability.get(t.id, set())),
        )
        for t in db_teachers
    ]

    # ---- Sections ----
    from academics.models import Section
    db_sections = Section.objects.filter(semester_id=semester_id, is_active=True)
    sections = [
        SectionData(id=s.id, name=s.name, student_count=s.student_count)
        for s in db_sections
    ]

    # ---- Activities (ClassSessions) ----
    # Each ClassSession with periods_per_week=N will produce N Placement records;
    # ActivityData itself is a single record — expansion happens in the algorithm.
    activities = []
    for cs in semester_sessions:
        # Determine required room type (from subject's session type if any)
        # Room type requirement is carried via Constraint rows; we check those below.
        # For now, ActivityData.room_type_required is None (constraints handle it).
        activities.append(
            ActivityData(
                id=cs.id,
                subject_name=cs.subject.name,
                section_id=cs.section_id,
                periods_per_week=cs.periods_per_week,
                teacher_id=cs.teacher_id,
                room_type_required=None,  # overridden below from Constraint rows
            )
        )

    # ---- Apply ROOM_TYPE_REQUIRED constraints to activities ----
    # Look up hard ROOM_TYPE_REQUIRED constraints scoped to subjects
    db_constraints = Constraint.objects.filter(
        semester_id=semester_id,
        is_active=True,
    ).select_related("teacher", "section", "subject", "room")

    # Build subject→required_room_type map (from hard ROOM_TYPE_REQUIRED constraints)
    subject_room_type: dict[int, str] = {}
    for c in db_constraints:
        if c.constraint_type == "ROOM_TYPE_REQUIRED" and c.is_hard and c.subject_id and c.required_room_type:
            subject_room_type[c.subject_id] = c.required_room_type

    # Re-build activities with room_type_required populated
    session_map = {cs.id: cs for cs in semester_sessions}
    activities = [
        ActivityData(
            id=a.id,
            subject_name=a.subject_name,
            section_id=a.section_id,
            periods_per_week=a.periods_per_week,
            teacher_id=a.teacher_id,
            room_type_required=subject_room_type.get(session_map[a.id].subject_id),
        )
        for a in activities
    ]

    # ---- Constraints ----
    constraints = [
        ConstraintData(
            id=c.id,
            constraint_type=c.constraint_type,
            is_hard=c.is_hard,
            weight=c.weight,
            teacher_id=c.teacher_id,
            section_id=c.section_id,
            max_daily_periods=c.max_daily_periods,
        )
        for c in db_constraints
    ]

    logger.info(
        "Loaded schedule input: %d timeslots, %d rooms, %d teachers, "
        "%d sections, %d activities, %d constraints",
        len(timeslots),
        len(rooms),
        len(teachers),
        len(sections),
        len(activities),
        len(constraints),
    )

    return ScheduleInput(
        timeslots=timeslots,
        rooms=rooms,
        teachers=teachers,
        sections=sections,
        activities=activities,
        constraints=constraints,
    )


# ---------------------------------------------------------------------------
# Public: ScheduleResult → TimetableSlot field dicts (unsaved)
# ---------------------------------------------------------------------------

def placements_to_slot_dicts(
    result: ScheduleResult,
    schedule_input: ScheduleInput,
    timetable_id: Optional[int] = None,
) -> list[dict]:
    """
    Convert a successful ScheduleResult into a list of field-value dicts
    matching the TimetableSlot model schema (to be defined in Prompt 11).

    Does NOT create or save any model instances.  The caller (view or
    management command) owns the transaction and calls
    TimetableSlot.objects.bulk_create(objs) after building instances from
    these dicts.

    Parameters
    ----------
    result : ScheduleResult
        Must have success=True; raises ValueError otherwise.
    schedule_input : ScheduleInput
        Used to look up teacher_id from activity_id (for denormalisation).
    timetable_id : int, optional
        If provided, included as 'timetable_id' in each dict so the caller
        can use the dicts directly for bulk_create without extra mapping.

    Returns
    -------
    list[dict]
        Each dict has keys:
          class_session_id, timeslot_id, room_id, teacher_id, is_manual,
          and optionally timetable_id.
    """
    if not result.success:
        raise ValueError(
            "placements_to_slot_dicts called on a failed ScheduleResult. "
            "Only call this when result.success is True."
        )

    slot_dicts = []
    for placement in result.placements:
        activity = schedule_input.activities_by_id.get(placement.activity_id)
        teacher_id = activity.teacher_id if activity else None

        d = {
            "class_session_id": placement.activity_id,
            "timeslot_id": placement.timeslot_id,
            "room_id": placement.room_id,
            "teacher_id": teacher_id,
            "is_manual": False,
        }
        if timetable_id is not None:
            d["timetable_id"] = timetable_id

        slot_dicts.append(d)

    return slot_dicts
