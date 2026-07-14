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
) -> bool:
    """
    Return True if the teacher has no other placement in this timeslot.

    Walks existing_placements so it operates on the current partial schedule
    without needing any look-up dict (kept simple; the list is small in
    practice — typically < 200 placements).
    """
    # We need the activity→teacher mapping, which callers supply via the
    # schedule_input; this low-level helper only checks teacher_id directly
    # against a pre-filtered list.  The caller (is_hard_feasible) passes
    # teacher_id explicitly.
    for p in existing_placements:
        if p.timeslot_id == slot_id and getattr(p, "_teacher_id", None) == teacher_id:
            return False
    return True


def section_not_double_booked(
    section_id: int,
    slot_id: int,
    existing_placements: list["Placement"],
    schedule_input: "ScheduleInput",
) -> bool:
    """
    Return True if the section has no other placement in this timeslot.
    """
    for p in existing_placements:
        if p.timeslot_id != slot_id:
            continue
        activity = schedule_input.activities_by_id.get(p.activity_id)
        if activity and activity.section_id == section_id:
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


def room_has_capacity(room: "RoomData", section_id: int, schedule_input: "ScheduleInput") -> bool:
    """
    Return True if the room has enough capacity for the section's student count.

    Falls back to True if section or capacity data is missing.
    """
    section = schedule_input.sections_by_id.get(section_id)
    if section is None:
        return True
    student_count = getattr(section, "student_count", 0)
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
      2. Section not already in another class in this slot
      3. Teacher available (not in unavailable set)
      4. Teacher not already teaching another class in this slot
      5. Room type satisfies activity's requirement
      6. Room capacity sufficient for section
      7. Teacher MAX_DAILY_HOURS constraints (from ConstraintData rows)
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

    # 1. Room double-booking
    for p in existing_placements:
        if p.timeslot_id == slot_id and p.room_id == room_id:
            return PlacementValidationResult(
                False,
                "room",
                room_id,
                f"Room {room.name} is already booked for this period.",
            )

    # 2. Section double-booking
    for p in existing_placements:
        if p.timeslot_id != slot_id:
            continue
        other_activity = schedule_input.activities_by_id.get(p.activity_id)
        if other_activity and other_activity.section_id == activity.section_id:
            section = schedule_input.sections_by_id.get(activity.section_id)
            section_name = section.name if section else f"#{activity.section_id}"
            return PlacementValidationResult(
                False,
                "section",
                activity.section_id,
                f"Section {section_name} already has a class in this period.",
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

        # 7. MAX_DAILY_HOURS hard constraints for this teacher
        for c in schedule_input.constraints:
            if (
                c.constraint_type == "MAX_DAILY_HOURS"
                and c.is_hard
                and c.teacher_id == activity.teacher_id
                and c.max_daily_periods is not None
            ):
                if not teacher_daily_limit_ok(
                    activity.teacher_id,
                    slot_id,
                    existing_placements,
                    schedule_input,
                    c.max_daily_periods,
                ):
                    return PlacementValidationResult(
                        False,
                        "teacher",
                        activity.teacher_id,
                        f"Teacher {teacher.name} would exceed the hard daily limit of {c.max_daily_periods} periods.",
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
    if not room_has_capacity(room, activity.section_id, schedule_input):
        section = schedule_input.sections_by_id.get(activity.section_id)
        section_name = section.name if section else f"#{activity.section_id}"
        return PlacementValidationResult(
            False,
            "room",
            room_id,
            f"Room {room.name} does not have enough capacity for section {section_name}.",
        )

    return PlacementValidationResult(True)


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
    slot_to_sections: dict[int, list[int]] = defaultdict(list)
    slot_to_teachers: dict[int, list[int]] = defaultdict(list)
    teacher_day_counts: dict[tuple[int, int], int] = defaultdict(int)

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

        # Section double-booking
        if activity.section_id in slot_to_sections[p.timeslot_id]:
            violations.append(
                f"HARD VIOLATION: Section {activity.section_id} double-booked in timeslot {p.timeslot_id}"
            )
        slot_to_sections[p.timeslot_id].append(activity.section_id)

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

                # Daily limit from hard MAX_DAILY_HOURS constraints
                teacher_day_counts[(activity.teacher_id, slot.day_of_week)] += 1

        # Room type
        if not room_type_matches(room, activity.room_type_required):
            violations.append(
                f"HARD VIOLATION: Room {room.name!r} type={room.room_type!r} does not satisfy "
                f"required type={activity.room_type_required!r} for activity={p.activity_id}"
            )

    # MAX_DAILY_HOURS hard constraint audit (post-placement)
    for c in schedule_input.constraints:
        if (
            c.constraint_type == "MAX_DAILY_HOURS"
            and c.is_hard
            and c.teacher_id is not None
            and c.max_daily_periods is not None
        ):
            for day in range(1, 6):
                count = teacher_day_counts.get((c.teacher_id, day), 0)
                if count > c.max_daily_periods:
                    violations.append(
                        f"HARD VIOLATION: Teacher {c.teacher_id} has {count} periods on day {day}, "
                        f"exceeds hard limit of {c.max_daily_periods}"
                    )

    return violations


# ---------------------------------------------------------------------------
# Soft-constraint penalty computation
# ---------------------------------------------------------------------------

def compute_penalty(
    placements: list["Placement"],
    schedule_input: "ScheduleInput",
) -> int:
    """
    Compute the total soft-constraint penalty for a complete placement set.

    Returns an integer >= 0.  Higher means more soft-constraint violations.

    Soft constraints evaluated:
      MAX_DAILY_HOURS (soft)  — each extra period beyond limit adds `weight` per excess
      NO_ADJACENT_GAPS (soft) — each day-gap in teacher's schedule adds `weight`
      MAX_CONSECUTIVE_PERIODS (soft) — excess longest consecutive run adds `weight`
      PREFERRED_TEACHING_TIME (soft) — each out-of-window placement adds `weight`

    Hard constraints are NOT counted here (they must be zero by the time
    this function is called).
    """
    penalty = 0

    # Build day-period lists per teacher and per section for gap detection
    teacher_day_periods: dict[tuple[int, int], list[int]] = defaultdict(list)
    section_day_periods: dict[tuple[int, int], list[int]] = defaultdict(list)
    teacher_day_counts: dict[tuple[int, int], int] = defaultdict(int)

    for p in placements:
        activity = schedule_input.activities_by_id.get(p.activity_id)
        slot = schedule_input.timeslots_by_id.get(p.timeslot_id)
        if activity is None or slot is None:
            continue

        if activity.teacher_id is not None:
            key = (activity.teacher_id, slot.day_of_week)
            teacher_day_periods[key].append(slot.period_number)
            teacher_day_counts[key] += 1

        section_key = (activity.section_id, slot.day_of_week)
        section_day_periods[section_key].append(slot.period_number)

    # Evaluate soft constraints
    for c in schedule_input.constraints:
        if c.is_hard:
            continue  # Hard constraints don't contribute to penalty

        if c.constraint_type == "MAX_DAILY_HOURS" and c.max_daily_periods is not None:
            # Penalise each period the teacher exceeds their daily soft limit
            if c.teacher_id is not None:
                for day in range(1, 6):
                    count = teacher_day_counts.get((c.teacher_id, day), 0)
                    excess = max(0, count - c.max_daily_periods)
                    penalty += excess * c.weight
            else:
                # Global soft daily limit — applies to all teachers
                for (tid, day), count in teacher_day_counts.items():
                    excess = max(0, count - c.max_daily_periods)
                    penalty += excess * c.weight

        elif c.constraint_type == "NO_ADJACENT_GAPS":
            # Penalise each gap (non-consecutive period) in a teacher's daily schedule
            if c.teacher_id is not None:
                for day in range(1, 6):
                    periods = sorted(teacher_day_periods.get((c.teacher_id, day), []))
                    gaps = _count_gaps(periods)
                    penalty += gaps * c.weight
            else:
                # Apply to all teachers
                for (tid, day), periods in teacher_day_periods.items():
                    gaps = _count_gaps(sorted(periods))
                    penalty += gaps * c.weight

        elif c.constraint_type == "MAX_CONSECUTIVE_PERIODS" and c.max_consecutive_periods is not None:
            if c.teacher_id is not None:
                teacher_ids = [c.teacher_id]
            else:
                teacher_ids = sorted({tid for (tid, _day) in teacher_day_periods})

            for teacher_id in teacher_ids:
                for day in range(1, 6):
                    periods = sorted(teacher_day_periods.get((teacher_id, day), []))
                    longest_run = _longest_consecutive_run(periods)
                    excess = max(0, longest_run - c.max_consecutive_periods)
                    penalty += excess * c.weight

        elif c.constraint_type == "PREFERRED_TEACHING_TIME":
            if c.preferred_period_start is None or c.preferred_period_end is None:
                continue

            for p in placements:
                activity = schedule_input.activities_by_id.get(p.activity_id)
                slot = schedule_input.timeslots_by_id.get(p.timeslot_id)
                if activity is None or slot is None or activity.teacher_id is None:
                    continue
                if c.teacher_id is not None and activity.teacher_id != c.teacher_id:
                    continue

                outside_preferred_day = bool(c.preferred_days) and slot.day_of_week not in c.preferred_days
                outside_preferred_period = (
                    slot.period_number < c.preferred_period_start
                    or slot.period_number > c.preferred_period_end
                )
                if outside_preferred_day or outside_preferred_period:
                    penalty += c.weight

    return penalty


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
