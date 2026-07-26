"""
scheduling/engine/constraints.py

Pure-Python constraint checking functions for the scheduling engine.

HARD constraint functions return True (feasible) or False (violated).
SOFT constraint functions return an integer penalty score (0 = no violation).

No Django imports are permitted in this file.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .data_types import (
        ActivityData,
        ConstraintData,
        Placement,
        RoomData,
        ScheduleInput,
        TeacherData,
        TimeSlotData,
    )


# ---------------------------------------------------------------------------
# Hard constraint helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlacementValidationResult:
    """Diagnostic result for one proposed placement."""
    is_valid: bool
    resource_type: str = ""
    resource_id: int | None = None
    message: str = ""

def timeslot_fits_shift(slot: "TimeSlotData", shift: str | None) -> bool:
    """
    Return True if the timeslot lies inside the cohort's day-shift window.

    Morning: 07:00–14:00 inclusive.
    Day:     09:00–16:00 inclusive.
    None / unknown shift: no restriction.
    """
    if not shift:
        return True
    start = slot.start_time
    end = slot.end_time
    if shift == "MORNING":
        return start >= "07:00" and end <= "14:00"
    if shift == "DAY":
        return start >= "09:00" and end <= "16:00"
    return True


def teacher_available(teacher: "TeacherData", slot_id: int) -> bool:
    """
    Return True if the teacher is available during the given timeslot.

    A teacher is unavailable if the slot_id appears in their
    `unavailable_slot_ids` frozenset (loaded from TeacherAvailability rows
    where is_available=False, or absent rows when defaults are unavailable).
    """
    return slot_id not in teacher.unavailable_slot_ids


def teacher_not_double_booked(
    teacher_id: int,
    slot_id: int,
    existing_placements: list["Placement"],
    schedule_input: "ScheduleInput",
) -> bool:
    """
    Return True if the teacher has no other placement in this timeslot.
    """
    for p in existing_placements:
        if p.timeslot_id != slot_id:
            continue
        activity = schedule_input.activities_by_id.get(p.activity_id)
        if activity and activity.teacher_id == teacher_id:
            return False
    return True


def course_level_not_double_booked(
    course_level_id: int,
    slot_id: int,
    existing_placements: list["Placement"],
    schedule_input: "ScheduleInput",
) -> bool:
    """
    Return True if the course level has no other placement in this timeslot.
    """
    for p in existing_placements:
        if p.timeslot_id != slot_id:
            continue
        activity = schedule_input.activities_by_id.get(p.activity_id)
        if activity and activity.course_level_id == course_level_id:
            return False
    return True


def room_not_double_booked(
    room_id: int,
    slot_id: int,
    existing_placements: list["Placement"],
) -> bool:
    """
    Return True if the room has no other placement in this timeslot.
    """
    for p in existing_placements:
        if p.timeslot_id == slot_id and p.room_id == room_id:
            return False
    return True


def room_type_matches(room: "RoomData", required_type: str | None) -> bool:
    """
    Return True if the room satisfies the required room type.

    If required_type is None the activity accepts any room.
    LAB activities may also be placed in COMPUTER_LAB rooms (superset).
    """
    if required_type is None:
        return True
    if room.room_type == required_type:
        return True
    # Allow COMPUTER_LAB to satisfy a LAB requirement
    if required_type == "LAB" and room.room_type == "COMPUTER_LAB":
        return True
    return False


def room_has_capacity(room: "RoomData", course_level_id: int, schedule_input: "ScheduleInput") -> bool:
    """
    Return True if the room has enough capacity for the course level's student count.

    Falls back to True if course level or capacity data is missing.
    """
    course_level = schedule_input.course_levels_by_id.get(course_level_id)
    if course_level is None:
        return True
    student_count = getattr(course_level, "student_count", 0)
    if student_count == 0:
        return True
    return room.capacity >= student_count


def teacher_daily_limit_ok(
    teacher_id: int,
    target_slot_id: int,
    existing_placements: list["Placement"],
    schedule_input: "ScheduleInput",
    max_daily_periods: int,
) -> bool:
    """
    Return True if adding this slot does not exceed the teacher's daily period limit.

    Counts how many periods the teacher already has on the same day as target_slot,
    then checks that count + 1 <= max_daily_periods.
    """
    target_slot = schedule_input.timeslots_by_id.get(target_slot_id)
    if target_slot is None:
        return True
    target_day = target_slot.day_of_week

    day_count = 0
    for p in existing_placements:
        activity = schedule_input.activities_by_id.get(p.activity_id)
        if activity is None:
            continue
        if activity.teacher_id != teacher_id:
            continue
        slot = schedule_input.timeslots_by_id.get(p.timeslot_id)
        if slot and slot.day_of_week == target_day:
            day_count += 1

    return (day_count + 1) <= max_daily_periods


def teacher_weekly_limit_ok(
    teacher_id: int,
    existing_placements: list["Placement"],
    schedule_input: "ScheduleInput",
    max_weekly_periods: int,
) -> bool:
    """Return True if adding one more period does not exceed the weekly limit."""
    week_count = 0
    for p in existing_placements:
        activity = schedule_input.activities_by_id.get(p.activity_id)
        if activity is not None and activity.teacher_id == teacher_id:
            week_count += 1
    return (week_count + 1) <= max_weekly_periods


def course_level_daily_limit_ok(
    course_level_id: int,
    target_slot_id: int,
    existing_placements: list["Placement"],
    schedule_input: "ScheduleInput",
    max_daily_periods: int,
) -> bool:
    """Return True if adding this slot does not exceed a course-level daily limit."""
    target_slot = schedule_input.timeslots_by_id.get(target_slot_id)
    if target_slot is None:
        return True
    day_count = 0
    for p in existing_placements:
        activity = schedule_input.activities_by_id.get(p.activity_id)
        if activity is None or activity.course_level_id != course_level_id:
            continue
        slot = schedule_input.timeslots_by_id.get(p.timeslot_id)
        if slot and slot.day_of_week == target_slot.day_of_week:
            day_count += 1
    return (day_count + 1) <= max_daily_periods


def _periods_on_day_for_teacher(
    teacher_id: int,
    day_of_week: int,
    existing_placements: list["Placement"],
    schedule_input: "ScheduleInput",
    extra_period: int | None = None,
) -> list[int]:
    periods: list[int] = []
    for p in existing_placements:
        activity = schedule_input.activities_by_id.get(p.activity_id)
        slot = schedule_input.timeslots_by_id.get(p.timeslot_id)
        if activity is None or slot is None:
            continue
        if activity.teacher_id == teacher_id and slot.day_of_week == day_of_week:
            periods.append(slot.period_number)
    if extra_period is not None:
        periods.append(extra_period)
    periods.sort()
    return periods


def _periods_on_day_for_course_level(
    course_level_id: int,
    day_of_week: int,
    existing_placements: list["Placement"],
    schedule_input: "ScheduleInput",
    extra_period: int | None = None,
) -> list[int]:
    periods: list[int] = []
    for p in existing_placements:
        activity = schedule_input.activities_by_id.get(p.activity_id)
        slot = schedule_input.timeslots_by_id.get(p.timeslot_id)
        if activity is None or slot is None:
            continue
        if activity.course_level_id == course_level_id and slot.day_of_week == day_of_week:
            periods.append(slot.period_number)
    if extra_period is not None:
        periods.append(extra_period)
    periods.sort()
    return periods


def _constraint_targets_teacher(constraint: "ConstraintData", teacher_id: int | None) -> bool:
    """True when a teacher-scoped/global constraint applies to this teacher."""
    if teacher_id is None:
        return False
    if constraint.teacher_id is not None:
        return constraint.teacher_id == teacher_id
    # Global (no teacher / course-level target) applies to every teacher.
    return constraint.course_level_id is None


def _preferred_time_ok(constraint: "ConstraintData", slot: "TimeSlotData") -> bool:
    if constraint.preferred_period_start is None or constraint.preferred_period_end is None:
        return True
    outside_day = bool(constraint.preferred_days) and slot.day_of_week not in constraint.preferred_days
    outside_period = (
        slot.period_number < constraint.preferred_period_start
        or slot.period_number > constraint.preferred_period_end
    )
    return not (outside_day or outside_period)


# ---------------------------------------------------------------------------
# Composite hard-feasibility check
# ---------------------------------------------------------------------------

def is_hard_feasible(
    activity: "ActivityData",
    slot_id: int,
    room_id: int,
    existing_placements: list["Placement"],
    schedule_input: "ScheduleInput",
) -> bool:
    """
    Return True only if ALL hard constraints pass for placing `activity` at
    (slot_id, room_id) given the current partial schedule.

    Checks performed (in short-circuit order for performance):
      1. Room not already occupied in this slot
      2. Course level not already in another class in this slot
      3. Teacher available (not in unavailable set)
      4. Teacher not already teaching another class in this slot
      5. Room type satisfies activity's requirement
      6. Room capacity sufficient for course level
      7. Teacher MAX_DAILY_PERIODS / MAX_WEEKLY_PERIODS constraints (from ConstraintData rows)
    """
    return validate_single_placement(
        activity,
        slot_id,
        room_id,
        existing_placements,
        schedule_input,
    ).is_valid


def validate_single_placement(
    activity: "ActivityData",
    slot_id: int,
    room_id: int,
    existing_placements: list["Placement"],
    schedule_input: "ScheduleInput",
) -> PlacementValidationResult:
    """
    Validate one proposed placement and return the first hard-constraint failure.

    This is the diagnostic companion to `is_hard_feasible`; keep all hard checks
    here so the generator and editor use the same placement rules.
    """
    slot = schedule_input.timeslots_by_id.get(slot_id)
    if slot is None:
        return PlacementValidationResult(False, "timeslot", slot_id, "Target time slot does not exist.")

    room = schedule_input.rooms_by_id.get(room_id)
    if room is None:
        return PlacementValidationResult(False, "room", room_id, "Target room does not exist.")

    # 0. Course-level day shift (Morning 7–2 / Day 9–5)
    course_level = schedule_input.course_levels_by_id.get(activity.course_level_id)
    if course_level is not None and not timeslot_fits_shift(slot, getattr(course_level, "shift", None)):
        shift = course_level.shift or "DAY"
        window = "7:00–14:00" if shift == "MORNING" else "9:00–16:00"
        return PlacementValidationResult(
            False,
            "course_level",
            activity.course_level_id,
            f"This cohort is {shift.title()} shift ({window}); the selected period is outside that window.",
        )

    # 1. Room double-booking
    for p in existing_placements:
        if p.timeslot_id == slot_id and p.room_id == room_id:
            return PlacementValidationResult(
                False,
                "room",
                room_id,
                f"Room {room.name} is already booked for this period.",
            )

    # 2. Course level double-booking
    for p in existing_placements:
        if p.timeslot_id != slot_id:
            continue
        other_activity = schedule_input.activities_by_id.get(p.activity_id)
        if other_activity and other_activity.course_level_id == activity.course_level_id:
            course_level = schedule_input.course_levels_by_id.get(activity.course_level_id)
            course_level_name = course_level.name if course_level else f"#{activity.course_level_id}"
            return PlacementValidationResult(
                False,
                "course_level",
                activity.course_level_id,
                f"Course level {course_level_name} already has a class in this period.",
            )

    # 3 & 4. Teacher checks (only if a teacher is assigned)
    if activity.teacher_id is not None:
        teacher = schedule_input.teachers_by_id.get(activity.teacher_id)
        if teacher is None:
            return PlacementValidationResult(
                False,
                "teacher",
                activity.teacher_id,
                "The assigned teacher is not available for scheduling.",
            )
        if not teacher_available(teacher, slot_id):
            return PlacementValidationResult(
                False,
                "teacher",
                activity.teacher_id,
                f"Teacher {teacher.name} is unavailable for this period.",
            )
        # Check teacher double-booking using annotated placements
        for p in existing_placements:
            if p.timeslot_id == slot_id:
                other_act = schedule_input.activities_by_id.get(p.activity_id)
                if other_act and other_act.teacher_id == activity.teacher_id:
                    return PlacementValidationResult(
                        False,
                        "teacher",
                        activity.teacher_id,
                        f"Teacher {teacher.name} is already teaching another class in this period.",
                    )

        # Profile daily cap (TeacherProfile.max_periods_per_day) is always hard.
        if not teacher_daily_limit_ok(
            activity.teacher_id,
            slot_id,
            existing_placements,
            schedule_input,
            teacher.max_periods_per_day,
        ):
            return PlacementValidationResult(
                False,
                "teacher",
                activity.teacher_id,
                f"Teacher {teacher.name} would exceed the daily limit of {teacher.max_periods_per_day} periods.",
            )

    # 5. Room type requirement
    if not room_type_matches(room, activity.room_type_required):
        return PlacementValidationResult(
            False,
            "room",
            room_id,
            f"Room {room.name} does not satisfy the required room type.",
        )

    # 6. Room capacity
    if not room_has_capacity(room, activity.course_level_id, schedule_input):
        course_level = schedule_input.course_levels_by_id.get(activity.course_level_id)
        course_level_name = course_level.name if course_level else f"#{activity.course_level_id}"
        return PlacementValidationResult(
            False,
            "room",
            room_id,
            f"Room {room.name} does not have enough capacity for course level {course_level_name}.",
        )

    # 7. Explicit hard Constraint rows (daily/weekly/gaps/consecutive/preferred)
    hard_failure = _hard_constraint_failure(
        activity, slot, existing_placements, schedule_input,
    )
    if hard_failure is not None:
        return hard_failure

    return PlacementValidationResult(True)


def _hard_constraint_failure(
    activity: "ActivityData",
    slot: "TimeSlotData",
    existing_placements: list["Placement"],
    schedule_input: "ScheduleInput",
) -> PlacementValidationResult | None:
    """Return the first hard Constraint-row failure for this candidate placement."""
    teacher = (
        schedule_input.teachers_by_id.get(activity.teacher_id)
        if activity.teacher_id is not None
        else None
    )

    for c in schedule_input.constraints:
        if not c.is_hard:
            continue

        if c.constraint_type == "MAX_DAILY_PERIODS" and c.max_daily_periods is not None:
            if c.course_level_id is not None:
                if c.course_level_id == activity.course_level_id and not course_level_daily_limit_ok(
                    activity.course_level_id,
                    slot.id,
                    existing_placements,
                    schedule_input,
                    c.max_daily_periods,
                ):
                    return PlacementValidationResult(
                        False,
                        "course_level",
                        activity.course_level_id,
                        f"Course level would exceed the hard daily limit of {c.max_daily_periods} periods.",
                    )
            elif _constraint_targets_teacher(c, activity.teacher_id):
                if not teacher_daily_limit_ok(
                    activity.teacher_id,
                    slot.id,
                    existing_placements,
                    schedule_input,
                    c.max_daily_periods,
                ):
                    name = teacher.name if teacher else f"#{activity.teacher_id}"
                    return PlacementValidationResult(
                        False,
                        "teacher",
                        activity.teacher_id,
                        f"Teacher {name} would exceed the hard daily limit of {c.max_daily_periods} periods.",
                    )

        elif c.constraint_type == "MAX_WEEKLY_PERIODS" and c.max_weekly_periods is not None:
            if _constraint_targets_teacher(c, activity.teacher_id):
                if not teacher_weekly_limit_ok(
                    activity.teacher_id,
                    existing_placements,
                    schedule_input,
                    c.max_weekly_periods,
                ):
                    name = teacher.name if teacher else f"#{activity.teacher_id}"
                    return PlacementValidationResult(
                        False,
                        "teacher",
                        activity.teacher_id,
                        f"Teacher {name} would exceed the hard weekly limit of {c.max_weekly_periods} periods.",
                    )

        elif c.constraint_type == "NO_ADJACENT_GAPS":
            if c.course_level_id is not None:
                if c.course_level_id == activity.course_level_id:
                    periods = _periods_on_day_for_course_level(
                        activity.course_level_id,
                        slot.day_of_week,
                        existing_placements,
                        schedule_input,
                        extra_period=slot.period_number,
                    )
                    if _count_gaps(periods) > 0:
                        return PlacementValidationResult(
                            False,
                            "course_level",
                            activity.course_level_id,
                            "Hard rule: course-level schedule cannot contain gaps on this day.",
                        )
            elif _constraint_targets_teacher(c, activity.teacher_id):
                periods = _periods_on_day_for_teacher(
                    activity.teacher_id,
                    slot.day_of_week,
                    existing_placements,
                    schedule_input,
                    extra_period=slot.period_number,
                )
                if _count_gaps(periods) > 0:
                    name = teacher.name if teacher else f"#{activity.teacher_id}"
                    return PlacementValidationResult(
                        False,
                        "teacher",
                        activity.teacher_id,
                        f"Hard rule: {name}'s schedule cannot contain gaps on this day.",
                    )

        elif c.constraint_type == "MAX_CONSECUTIVE_PERIODS" and c.max_consecutive_periods is not None:
            if _constraint_targets_teacher(c, activity.teacher_id):
                periods = _periods_on_day_for_teacher(
                    activity.teacher_id,
                    slot.day_of_week,
                    existing_placements,
                    schedule_input,
                    extra_period=slot.period_number,
                )
                if _longest_consecutive_run(periods) > c.max_consecutive_periods:
                    name = teacher.name if teacher else f"#{activity.teacher_id}"
                    return PlacementValidationResult(
                        False,
                        "teacher",
                        activity.teacher_id,
                        f"Teacher {name} would exceed {c.max_consecutive_periods} consecutive periods.",
                    )

        elif c.constraint_type == "PREFERRED_TEACHING_TIME":
            if _constraint_targets_teacher(c, activity.teacher_id) and not _preferred_time_ok(c, slot):
                name = teacher.name if teacher else f"#{activity.teacher_id}"
                return PlacementValidationResult(
                    False,
                    "teacher",
                    activity.teacher_id,
                    f"Teacher {name} can only be scheduled in their preferred teaching window.",
                )

    return None


# ---------------------------------------------------------------------------
# Hard-constraint audit (called after a successful run for safety)
# ---------------------------------------------------------------------------

def find_hard_violations(
    placements: list["Placement"],
    schedule_input: "ScheduleInput",
) -> list[str]:
    """
    Audit a complete set of placements for hard-constraint violations.

    Returns a list of human-readable violation descriptions.  An empty list
    means the schedule is hard-constraint-clean.

    This is the final safety gate called in algorithm.py before a
    success=True result is returned.
    """
    violations: list[str] = []

    # Index placements by slot for efficient O(n) checks
    slot_to_rooms: dict[int, list[int]] = defaultdict(list)
    slot_to_course_levels: dict[int, list[int]] = defaultdict(list)
    slot_to_teachers: dict[int, list[int]] = defaultdict(list)
    teacher_day_counts: dict[tuple[int, int], int] = defaultdict(int)
    teacher_week_counts: dict[int, int] = defaultdict(int)

    for p in placements:
        activity = schedule_input.activities_by_id.get(p.activity_id)
        if activity is None:
            violations.append(f"Placement references unknown activity_id={p.activity_id}")
            continue

        slot = schedule_input.timeslots_by_id.get(p.timeslot_id)
        if slot is None:
            violations.append(
                f"Placement for activity={p.activity_id} references unknown timeslot_id={p.timeslot_id}"
            )
            continue

        room = schedule_input.rooms_by_id.get(p.room_id)
        if room is None:
            violations.append(
                f"Placement for activity={p.activity_id} references unknown room_id={p.room_id}"
            )
            continue

        # Room double-booking
        if p.room_id in slot_to_rooms[p.timeslot_id]:
            violations.append(
                f"HARD VIOLATION: Room {room.name!r} double-booked in timeslot {p.timeslot_id}"
            )
        slot_to_rooms[p.timeslot_id].append(p.room_id)

        # Course level double-booking
        if activity.course_level_id in slot_to_course_levels[p.timeslot_id]:
            violations.append(
                f"HARD VIOLATION: Course level {activity.course_level_id} double-booked in timeslot {p.timeslot_id}"
            )
        slot_to_course_levels[p.timeslot_id].append(activity.course_level_id)

        # Teacher availability + double-booking
        if activity.teacher_id is not None:
            teacher = schedule_input.teachers_by_id.get(activity.teacher_id)
            if teacher:
                if not teacher_available(teacher, p.timeslot_id):
                    violations.append(
                        f"HARD VIOLATION: Teacher {teacher.name!r} placed in unavailable timeslot {p.timeslot_id}"
                    )
                if activity.teacher_id in slot_to_teachers[p.timeslot_id]:
                    violations.append(
                        f"HARD VIOLATION: Teacher {teacher.name!r} double-booked in timeslot {p.timeslot_id}"
                    )
                slot_to_teachers[p.timeslot_id].append(activity.teacher_id)

                # Daily / weekly counts for hard limit audits
                teacher_day_counts[(activity.teacher_id, slot.day_of_week)] += 1
                teacher_week_counts[activity.teacher_id] += 1

        # Room type
        if not room_type_matches(room, activity.room_type_required):
            violations.append(
                f"HARD VIOLATION: Room {room.name!r} type={room.room_type!r} does not satisfy "
                f"required type={activity.room_type_required!r} for activity={p.activity_id}"
            )

        # Capacity
        if not room_has_capacity(room, activity.course_level_id, schedule_input):
            violations.append(
                f"HARD VIOLATION: Room {room.name!r} lacks capacity for course level "
                f"{activity.course_level_id} (activity={p.activity_id})"
            )

        # Day-shift window
        course_level = schedule_input.course_levels_by_id.get(activity.course_level_id)
        if course_level is not None and not timeslot_fits_shift(slot, getattr(course_level, "shift", None)):
            violations.append(
                f"HARD VIOLATION: Activity {p.activity_id} placed outside "
                f"{course_level.shift or 'DAY'} shift window in timeslot {p.timeslot_id}"
            )

    # Profile daily hard-cap audit
    for (tid, day), count in teacher_day_counts.items():
        teacher = schedule_input.teachers_by_id.get(tid)
        if teacher and count > teacher.max_periods_per_day:
            violations.append(
                f"HARD VIOLATION: Teacher {teacher.name!r} has {count} periods on day {day}, "
                f"exceeds profile daily limit of {teacher.max_periods_per_day}"
            )

    # Explicit hard Constraint-row audit
    course_level_day_counts: dict[tuple[int, int], int] = defaultdict(int)
    teacher_day_periods: dict[tuple[int, int], list[int]] = defaultdict(list)
    course_level_day_periods: dict[tuple[int, int], list[int]] = defaultdict(list)
    for p in placements:
        activity = schedule_input.activities_by_id.get(p.activity_id)
        slot = schedule_input.timeslots_by_id.get(p.timeslot_id)
        if activity is None or slot is None:
            continue
        course_level_day_counts[(activity.course_level_id, slot.day_of_week)] += 1
        course_level_day_periods[(activity.course_level_id, slot.day_of_week)].append(slot.period_number)
        if activity.teacher_id is not None:
            teacher_day_periods[(activity.teacher_id, slot.day_of_week)].append(slot.period_number)

    for periods in teacher_day_periods.values():
        periods.sort()
    for periods in course_level_day_periods.values():
        periods.sort()

    for c in schedule_input.constraints:
        if not c.is_hard:
            continue

        if c.constraint_type == "MAX_DAILY_PERIODS" and c.max_daily_periods is not None:
            if c.course_level_id is not None:
                for day in range(1, 6):
                    count = course_level_day_counts.get((c.course_level_id, day), 0)
                    if count > c.max_daily_periods:
                        violations.append(
                            f"HARD VIOLATION: Course level {c.course_level_id} has {count} periods "
                            f"on day {day}, exceeds hard limit of {c.max_daily_periods}"
                        )
            elif c.teacher_id is not None:
                for day in range(1, 6):
                    count = teacher_day_counts.get((c.teacher_id, day), 0)
                    if count > c.max_daily_periods:
                        violations.append(
                            f"HARD VIOLATION: Teacher {c.teacher_id} has {count} periods on day {day}, "
                            f"exceeds hard limit of {c.max_daily_periods}"
                        )
            else:
                for (tid, day), count in teacher_day_counts.items():
                    if count > c.max_daily_periods:
                        violations.append(
                            f"HARD VIOLATION: Teacher {tid} has {count} periods on day {day}, "
                            f"exceeds global hard daily limit of {c.max_daily_periods}"
                        )

        elif c.constraint_type == "MAX_WEEKLY_PERIODS" and c.max_weekly_periods is not None:
            if c.teacher_id is not None:
                count = teacher_week_counts.get(c.teacher_id, 0)
                if count > c.max_weekly_periods:
                    violations.append(
                        f"HARD VIOLATION: Teacher {c.teacher_id} has {count} periods this week, "
                        f"exceeds hard limit of {c.max_weekly_periods}"
                    )
            elif c.course_level_id is None:
                for tid, count in teacher_week_counts.items():
                    if count > c.max_weekly_periods:
                        violations.append(
                            f"HARD VIOLATION: Teacher {tid} has {count} periods this week, "
                            f"exceeds global hard weekly limit of {c.max_weekly_periods}"
                        )

        elif c.constraint_type == "NO_ADJACENT_GAPS":
            if c.course_level_id is not None:
                for day in range(1, 6):
                    periods = course_level_day_periods.get((c.course_level_id, day), [])
                    if _count_gaps(periods) > 0:
                        violations.append(
                            f"HARD VIOLATION: Course level {c.course_level_id} has gaps on day {day}"
                        )
            elif c.teacher_id is not None:
                for day in range(1, 6):
                    periods = teacher_day_periods.get((c.teacher_id, day), [])
                    if _count_gaps(periods) > 0:
                        violations.append(
                            f"HARD VIOLATION: Teacher {c.teacher_id} has gaps on day {day}"
                        )
            else:
                for (tid, day), periods in teacher_day_periods.items():
                    if _count_gaps(periods) > 0:
                        violations.append(
                            f"HARD VIOLATION: Teacher {tid} has gaps on day {day}"
                        )

        elif c.constraint_type == "MAX_CONSECUTIVE_PERIODS" and c.max_consecutive_periods is not None:
            teacher_ids = (
                [c.teacher_id]
                if c.teacher_id is not None
                else sorted({tid for (tid, _day) in teacher_day_periods})
            )
            for tid in teacher_ids:
                for day in range(1, 6):
                    periods = teacher_day_periods.get((tid, day), [])
                    if _longest_consecutive_run(periods) > c.max_consecutive_periods:
                        violations.append(
                            f"HARD VIOLATION: Teacher {tid} exceeds {c.max_consecutive_periods} "
                            f"consecutive periods on day {day}"
                        )

        elif c.constraint_type == "PREFERRED_TEACHING_TIME":
            for p in placements:
                activity = schedule_input.activities_by_id.get(p.activity_id)
                slot = schedule_input.timeslots_by_id.get(p.timeslot_id)
                if activity is None or slot is None:
                    continue
                if not _constraint_targets_teacher(c, activity.teacher_id):
                    continue
                if not _preferred_time_ok(c, slot):
                    violations.append(
                        f"HARD VIOLATION: Teacher {activity.teacher_id} placed outside preferred "
                        f"teaching window (activity={p.activity_id}, timeslot={p.timeslot_id})"
                    )

    return violations


# ---------------------------------------------------------------------------
# Soft-constraint penalty computation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SoftViolation:
    """One soft-constraint conflict for reporting / scoring."""
    constraint_type: str
    type_label: str
    type_icon: str
    teacher_id: int | None
    teacher_name: str
    day_label: str
    detail: str
    excess: int
    penalty: int


_DAY_NAMES = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
}


def collect_soft_violations(
    placements: list["Placement"],
    schedule_input: "ScheduleInput",
) -> list[SoftViolation]:
    """
    Enumerate soft-constraint conflicts for a placement set.

    Used by compute_penalty() and by the conflict-report UI so both agree.
    """
    teacher_day_periods: dict[tuple[int, int], list[int]] = defaultdict(list)
    course_level_day_periods: dict[tuple[int, int], list[int]] = defaultdict(list)
    teacher_day_counts: dict[tuple[int, int], int] = defaultdict(int)
    teacher_week_counts: dict[int, int] = defaultdict(int)

    for p in placements:
        activity = schedule_input.activities_by_id.get(p.activity_id)
        slot = schedule_input.timeslots_by_id.get(p.timeslot_id)
        if activity is None or slot is None:
            continue
        if activity.teacher_id is not None:
            key = (activity.teacher_id, slot.day_of_week)
            teacher_day_periods[key].append(slot.period_number)
            teacher_day_counts[key] += 1
            teacher_week_counts[activity.teacher_id] += 1
        course_level_day_periods[(activity.course_level_id, slot.day_of_week)].append(
            slot.period_number
        )

    for periods in teacher_day_periods.values():
        periods.sort()
    for periods in course_level_day_periods.values():
        periods.sort()

    def teacher_name(tid: int | None) -> str:
        if tid is None:
            return "—"
        teacher = schedule_input.teachers_by_id.get(tid)
        return teacher.name if teacher else f"Teacher #{tid}"

    violations: list[SoftViolation] = []

    for c in schedule_input.constraints:
        if c.is_hard:
            continue

        if c.constraint_type == "MAX_DAILY_PERIODS" and c.max_daily_periods is not None:
            if c.course_level_id is not None:
                for day in range(1, 6):
                    periods = course_level_day_periods.get((c.course_level_id, day), [])
                    excess = max(0, len(periods) - c.max_daily_periods)
                    if excess:
                        violations.append(SoftViolation(
                            constraint_type=c.constraint_type,
                            type_label="Max Daily Periods",
                            type_icon="bi-clock-history",
                            teacher_id=None,
                            teacher_name=f"Course level #{c.course_level_id}",
                            day_label=_DAY_NAMES.get(day, f"Day {day}"),
                            detail=(
                                f"{len(periods)} periods scheduled, "
                                f"soft limit is {c.max_daily_periods}"
                            ),
                            excess=excess,
                            penalty=excess * c.weight,
                        ))
            else:
                teacher_ids = (
                    [c.teacher_id]
                    if c.teacher_id is not None
                    else sorted({tid for (tid, _day) in teacher_day_counts})
                )
                for tid in teacher_ids:
                    for day in range(1, 6):
                        count = teacher_day_counts.get((tid, day), 0)
                        excess = max(0, count - c.max_daily_periods)
                        if excess:
                            violations.append(SoftViolation(
                                constraint_type=c.constraint_type,
                                type_label="Max Daily Periods",
                                type_icon="bi-clock-history",
                                teacher_id=tid,
                                teacher_name=teacher_name(tid),
                                day_label=_DAY_NAMES.get(day, f"Day {day}"),
                                detail=(
                                    f"{count} periods scheduled, "
                                    f"soft limit is {c.max_daily_periods}"
                                ),
                                excess=excess,
                                penalty=excess * c.weight,
                            ))

        elif c.constraint_type == "MAX_WEEKLY_PERIODS" and c.max_weekly_periods is not None:
            teacher_ids = (
                [c.teacher_id]
                if c.teacher_id is not None
                else sorted(teacher_week_counts)
            )
            for tid in teacher_ids:
                count = teacher_week_counts.get(tid, 0)
                excess = max(0, count - c.max_weekly_periods)
                if excess:
                    violations.append(SoftViolation(
                        constraint_type=c.constraint_type,
                        type_label="Max Weekly Periods",
                        type_icon="bi-calendar-week",
                        teacher_id=tid,
                        teacher_name=teacher_name(tid),
                        day_label="Week",
                        detail=(
                            f"{count} periods scheduled, "
                            f"soft weekly limit is {c.max_weekly_periods}"
                        ),
                        excess=excess,
                        penalty=excess * c.weight,
                    ))

        elif c.constraint_type == "NO_ADJACENT_GAPS":
            if c.course_level_id is not None:
                for day in range(1, 6):
                    periods = course_level_day_periods.get((c.course_level_id, day), [])
                    gaps = _count_gaps(periods)
                    if gaps:
                        violations.append(SoftViolation(
                            constraint_type=c.constraint_type,
                            type_label="Schedule Gap",
                            type_icon="bi-exclamation-triangle",
                            teacher_id=None,
                            teacher_name=f"Course level #{c.course_level_id}",
                            day_label=_DAY_NAMES.get(day, f"Day {day}"),
                            detail=f"{gaps} gap(s) in periods {periods}",
                            excess=gaps,
                            penalty=gaps * c.weight,
                        ))
            else:
                teacher_ids = (
                    [c.teacher_id]
                    if c.teacher_id is not None
                    else sorted({tid for (tid, _day) in teacher_day_periods})
                )
                for tid in teacher_ids:
                    for day in range(1, 6):
                        periods = teacher_day_periods.get((tid, day), [])
                        gaps = _count_gaps(periods)
                        if gaps:
                            violations.append(SoftViolation(
                                constraint_type=c.constraint_type,
                                type_label="Schedule Gap",
                                type_icon="bi-exclamation-triangle",
                                teacher_id=tid,
                                teacher_name=teacher_name(tid),
                                day_label=_DAY_NAMES.get(day, f"Day {day}"),
                                detail=f"{gaps} gap(s) in periods {periods}",
                                excess=gaps,
                                penalty=gaps * c.weight,
                            ))

        elif c.constraint_type == "MAX_CONSECUTIVE_PERIODS" and c.max_consecutive_periods is not None:
            teacher_ids = (
                [c.teacher_id]
                if c.teacher_id is not None
                else sorted({tid for (tid, _day) in teacher_day_periods})
            )
            for tid in teacher_ids:
                for day in range(1, 6):
                    periods = teacher_day_periods.get((tid, day), [])
                    longest = _longest_consecutive_run(periods)
                    excess = max(0, longest - c.max_consecutive_periods)
                    if excess:
                        violations.append(SoftViolation(
                            constraint_type=c.constraint_type,
                            type_label="Max Consecutive Periods",
                            type_icon="bi-hr",
                            teacher_id=tid,
                            teacher_name=teacher_name(tid),
                            day_label=_DAY_NAMES.get(day, f"Day {day}"),
                            detail=(
                                f"{longest} consecutive periods, "
                                f"soft limit is {c.max_consecutive_periods}"
                            ),
                            excess=excess,
                            penalty=excess * c.weight,
                        ))

        elif c.constraint_type == "PREFERRED_TEACHING_TIME":
            if c.preferred_period_start is None or c.preferred_period_end is None:
                continue
            for p in placements:
                activity = schedule_input.activities_by_id.get(p.activity_id)
                slot = schedule_input.timeslots_by_id.get(p.timeslot_id)
                if activity is None or slot is None:
                    continue
                if not _constraint_targets_teacher(c, activity.teacher_id):
                    continue
                if not _preferred_time_ok(c, slot):
                    violations.append(SoftViolation(
                        constraint_type=c.constraint_type,
                        type_label="Preferred Teaching Time",
                        type_icon="bi-heart",
                        teacher_id=activity.teacher_id,
                        teacher_name=teacher_name(activity.teacher_id),
                        day_label=_DAY_NAMES.get(slot.day_of_week, f"Day {slot.day_of_week}"),
                        detail=(
                            f"Period {slot.period_number} is outside preferred window "
                            f"(days={sorted(c.preferred_days) or 'any'}, "
                            f"periods {c.preferred_period_start}–{c.preferred_period_end})"
                        ),
                        excess=1,
                        penalty=c.weight,
                    ))

    violations.sort(key=lambda row: row.penalty, reverse=True)
    return violations


def compute_penalty(
    placements: list["Placement"],
    schedule_input: "ScheduleInput",
) -> int:
    """
    Compute the total soft-constraint penalty for a complete placement set.

    Returns an integer >= 0.  Higher means more soft-constraint violations.
    """
    return sum(v.penalty for v in collect_soft_violations(placements, schedule_input))


def _longest_consecutive_run(sorted_periods: list[int]) -> int:
    """Return the length of the longest consecutive period run."""
    if not sorted_periods:
        return 0
    longest = 1
    current = 1
    for i in range(1, len(sorted_periods)):
        if sorted_periods[i] == sorted_periods[i - 1] + 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def _count_gaps(sorted_periods: list[int]) -> int:
    """
    Count interior gaps in a sorted list of period numbers.

    Example: [1, 3, 4] → 1 gap (between periods 1 and 3).
    Example: [2, 3, 5] → 1 gap (between periods 3 and 5).
    Example: [1, 2, 3] → 0 gaps (consecutive).
    """
    if len(sorted_periods) <= 1:
        return 0
    gaps = 0
    for i in range(1, len(sorted_periods)):
        if sorted_periods[i] - sorted_periods[i - 1] > 1:
            gaps += 1
    return gaps
