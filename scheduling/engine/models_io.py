"""
scheduling/engine/models_io.py

ORM adapter — the ONLY file in scheduling/engine/ that may import Django models.

Responsibilities:
  1. load_schedule_input(session_id)  → ScheduleInput
     Reads ClassSession, TimeSlot, TeacherAvailability, Constraint, Room
     rows for the given session and converts them into the engine's internal
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
    CourseLevelData,
    RoomData,
    ScheduleInput,
    ScheduleResult,
    TeacherData,
    TimeSlotData,
)

logger = logging.getLogger(__name__)

def _constraint_data_from_model(constraint) -> ConstraintData:
    """Map one scheduling.Constraint ORM row to ConstraintData."""
    preferred_days = frozenset()
    preferred_period_start = None
    preferred_period_end = None

    if constraint.constraint_type == "PREFERRED_TEACHING_TIME":
        params = constraint.custom_parameters or {}
        preferred_days = frozenset(params.get("preferred_days", []))
        preferred_period_start = params.get("period_start")
        preferred_period_end = params.get("period_end")

    return ConstraintData(
        id=constraint.id,
        constraint_type=constraint.constraint_type,
        is_hard=constraint.is_hard,
        weight=constraint.weight,
        teacher_id=constraint.teacher_id,
        course_level_id=constraint.course_level_id,
        max_daily_periods=constraint.max_daily_periods,
        max_weekly_periods=constraint.max_weekly_periods,
        max_consecutive_periods=constraint.max_consecutive_periods,
        preferred_days=preferred_days,
        preferred_period_start=preferred_period_start,
        preferred_period_end=preferred_period_end,
    )


# ---------------------------------------------------------------------------
# Public: ORM → ScheduleInput
# ---------------------------------------------------------------------------

def load_schedule_input(session_id: int, school_id: int | None = None) -> ScheduleInput:
    """
    Load all data needed by the engine for a given session and return a
    ScheduleInput populated with pure-Python dataclasses.

    Raises
    ------
    ValueError
        If the session does not exist, has no active timeslots, or does not
        belong to the provided school_id.

    Usage
    -----
    >>> from scheduling.engine.models_io import load_schedule_input
    >>> from scheduling.engine.algorithm import run_scheduler
    >>> schedule_input = load_schedule_input(session_id=1)
    >>> result = run_scheduler(schedule_input)
    """
    # Import Django models here (and only here) so that the rest of the engine
    # package is importable without a configured Django application.
    from core.models import Room, Session
    from academics.models import ClassSession, CourseLevel, TeacherProfile
    from scheduling.models import Constraint, TeacherAvailability, TimeSlot

    # ---- Validate session exists ----
    try:
        session = Session.objects.get(pk=session_id)
    except Session.DoesNotExist:
        raise ValueError(f"Session with id={session_id} does not exist.")

    if school_id is not None and session.school_id != school_id:
        raise ValueError(
            f"Session with id={session_id} does not belong to school id={school_id}."
        )

    logger.info("Loading schedule input for session %r (id=%d)", session.name, session_id)

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
    # Session membership is via ClassSession.session.
    session_class_sessions = ClassSession.objects.filter(
        session_id=session_id,
    ).select_related("teacher", "course_level", "course_level__course", "subject")

    teacher_ids_in_session = set(
        s.teacher_id for s in session_class_sessions if s.teacher_id is not None
    )

    # Build unavailability map: teacher_id → frozenset of unavailable timeslot ids
    unavailability: dict[int, set[int]] = {tid: set() for tid in teacher_ids_in_session}
    db_avail = TeacherAvailability.objects.filter(
        teacher_id__in=teacher_ids_in_session,
        is_available=False,
    ).select_related("timeslot")
    for row in db_avail:
        unavailability.setdefault(row.teacher_id, set()).add(row.timeslot_id)

    db_teachers = TeacherProfile.objects.filter(
        pk__in=teacher_ids_in_session,
        is_active=True,
    ).select_related("user")

    teachers = [
        TeacherData(
            id=t.id,
            name=t.user.get_full_name() or t.user.username,
            max_periods_per_day=t.max_periods_per_day,
            unavailable_slot_ids=frozenset(unavailability.get(t.id, set())),
        )
        for t in db_teachers
    ]
    # ---- Course levels (cohorts referenced by this session's class sessions) ----
    from academics.models import CourseLevelOffering

    course_level_ids = {cs.course_level_id for cs in session_class_sessions}
    db_course_levels = CourseLevel.objects.filter(
        pk__in=course_level_ids,
        is_active=True,
    ).select_related("course")
    shift_by_level = {
        o.course_level_id: o.shift
        for o in CourseLevelOffering.objects.filter(
            session_id=session_id,
            course_level_id__in=course_level_ids,
        )
    }
    course_levels = [
        CourseLevelData(
            id=cl.id,
            name=str(cl),
            student_count=cl.student_count,
            course_id=cl.course_id,
            course_code=cl.course.code if cl.course_id else "",
            course_name=cl.course.name if cl.course_id else "",
            level=cl.level,
            # Default Day window when an offering row is missing
            shift=shift_by_level.get(cl.id, CourseLevelOffering.Shift.DAY),
        )
        for cl in db_course_levels
    ]
    course_levels_by_id = {cl.id: cl for cl in course_levels}

    # ---- Apply ROOM_TYPE_REQUIRED constraints to activities ----
    db_constraints = Constraint.objects.filter(
        session_id=session_id,
        is_active=True,
    ).select_related("teacher", "course_level", "subject", "room")

    subject_room_type: dict[int, str] = {}
    for c in db_constraints:
        if c.constraint_type == "ROOM_TYPE_REQUIRED" and c.is_hard and c.subject_id and c.required_room_type:
            subject_room_type[c.subject_id] = c.required_room_type

    # ---- Activities (ClassSessions) ----
    activities = []
    for cs in session_class_sessions:
        cl_data = course_levels_by_id.get(cs.course_level_id)
        activities.append(
            ActivityData(
                id=cs.id,
                subject_name=cs.subject.name,
                course_level_id=cs.course_level_id,
                periods_per_week=cs.periods_per_week,
                teacher_id=cs.teacher_id,
                room_type_required=subject_room_type.get(cs.subject_id),
                subject_code=cs.subject.code or "",
                course_code=(cl_data.course_code if cl_data else (cs.course_level.course.code if cs.course_level_id else "")),
                course_name=(cl_data.course_name if cl_data else (cs.course_level.course.name if cs.course_level_id else "")),
                semester=cl_data.level if cl_data else getattr(cs.course_level, "level", None),
                shift=cl_data.shift if cl_data else None,
            )
        )

    # ---- Constraints ----
    # TeacherProfile.max_periods_per_day is enforced as a hard cap in the engine
    # via TeacherData — no synthetic Constraint row is required.
    constraints = [_constraint_data_from_model(c) for c in db_constraints]

    logger.info(
        "Loaded schedule input: %d timeslots, %d rooms, %d teachers, "
        "%d course levels, %d activities, %d constraints",
        len(timeslots),
        len(rooms),
        len(teachers),
        len(course_levels),
        len(activities),
        len(constraints),
    )

    return ScheduleInput(
        timeslots=timeslots,
        rooms=rooms,
        teachers=teachers,
        course_levels=course_levels,
        activities=activities,
        constraints=constraints,
        session_name=session.name,
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
