"""
Human-readable scheduling failure diagnostics.

Explains why generation failed without dumping raw activity ID lists.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from .constraints import timeslot_fits_shift, validate_single_placement

if TYPE_CHECKING:
    from .data_types import ActivityData, ScheduleInput


def diagnose_infeasibility(schedule_input: "ScheduleInput", max_examples: int = 8) -> dict:
    """
    Analyse a ScheduleInput and return a structured failure report.

    Checks each class session in isolation (empty timetable). Sessions with
    zero feasible (timeslot, room) pairs are fundamentally blocked by hard
    rules — those are the best clues for the admin.
    """
    total_periods = sum(max(a.periods_per_week, 0) for a in schedule_input.activities)
    slot_count = len(schedule_input.timeslots)
    room_count = len(schedule_input.rooms)

    blocked: list[dict] = []
    reason_counts: Counter[str] = Counter()
    solo_feasible_period_demand = 0

    for activity in schedule_input.activities:
        feasible, top_reason = _solo_feasibility(activity, schedule_input)
        if feasible == 0:
            blocked.append(_activity_detail(
                activity,
                schedule_input,
                reason=top_reason or "No feasible timeslot/room combination.",
            ))
            reason_counts[_short_reason(top_reason)] += 1
        else:
            solo_feasible_period_demand += activity.periods_per_week

    overload_notes = _overload_notes(schedule_input)

    session_label = getattr(schedule_input, "session_name", "") or "active session"
    summary_parts = [
        f"Session: {session_label}.",
        f"{len(schedule_input.activities)} class sessions "
        f"({total_periods} periods/week) across "
        f"{slot_count} timeslots and {room_count} rooms.",
    ]
    if blocked:
        summary_parts.append(
            f"{len(blocked)} session(s) have no valid slot even when scheduled alone."
        )
    else:
        summary_parts.append(
            "Every session can be placed alone; failure is likely from "
            "over-constrained combinations (teacher load, hard preferred times, "
            "gap rules, or room contention)."
        )

    top_reasons = [
        {"reason": reason, "count": count}
        for reason, count in reason_counts.most_common(6)
    ]

    hard_constraints = [
        c for c in schedule_input.constraints if c.is_hard
    ]
    hard_constraint_notes = []
    for c in hard_constraints:
        label = c.constraint_type.replace("_", " ").title()
        scope = "all teachers"
        if c.teacher_id is not None:
            scope = _teacher_name(schedule_input, c.teacher_id)
        elif c.course_level_id is not None:
            scope = _course_level_name(schedule_input, c.course_level_id)
        hard_constraint_notes.append(f"{label} → {scope}")

    return {
        "summary": " ".join(summary_parts),
        "top_reasons": top_reasons,
        "blocked_examples": blocked[:max_examples],
        "blocked_count": len(blocked),
        "overload_notes": overload_notes,
        "hard_constraints": hard_constraint_notes[:12],
        "hard_constraint_count": len(hard_constraints),
        "suggestions": _suggestions(blocked, top_reasons, hard_constraint_notes, overload_notes),
    }


def format_diagnostic_message(report: dict, max_restarts: int) -> str:
    """Compact single-string message suitable for Django flash messages."""
    lines = [
        f"Could not build a complete timetable after {max_restarts} attempt(s).",
        report["summary"],
    ]

    if report["top_reasons"]:
        lines.append("Most common blockers:")
        for item in report["top_reasons"][:5]:
            lines.append(f"• {item['reason']} ({item['count']} session(s))")

    if report["blocked_examples"]:
        lines.append("Blocked class sessions:")
        for row in report["blocked_examples"][:5]:
            lines.append(f"• {row['label']}")
            lines.append(f"  Reason: {row['reason']}")

    if report["overload_notes"]:
        lines.append("Load pressure:")
        for note in report["overload_notes"][:4]:
            lines.append(f"• {note}")

    if report["suggestions"]:
        lines.append("Try:")
        for tip in report["suggestions"][:4]:
            lines.append(f"• {tip}")

    return "\n".join(lines)


def _solo_feasibility(activity: "ActivityData", schedule_input: "ScheduleInput") -> tuple[int, str]:
    feasible = 0
    fail_reasons: Counter[str] = Counter()
    for ts in schedule_input.timeslots:
        for room in schedule_input.rooms:
            result = validate_single_placement(
                activity, ts.id, room.id, [], schedule_input,
            )
            if result.is_valid:
                feasible += 1
            else:
                fail_reasons[result.message or "Unknown hard-constraint failure"] += 1
    top_reason = fail_reasons.most_common(1)[0][0] if fail_reasons else ""
    return feasible, top_reason


def _overload_notes(schedule_input: "ScheduleInput") -> list[str]:
    notes: list[str] = []
    slots_per_day: dict[int, int] = Counter(
        ts.day_of_week for ts in schedule_input.timeslots
    )
    total_slots = len(schedule_input.timeslots)

    # Teacher weekly demand vs available slots after unavailability
    teacher_demand: dict[int, int] = defaultdict(int)
    for activity in schedule_input.activities:
        if activity.teacher_id is not None:
            teacher_demand[activity.teacher_id] += activity.periods_per_week

    for teacher_id, demand in sorted(teacher_demand.items(), key=lambda x: -x[1]):
        teacher = schedule_input.teachers_by_id.get(teacher_id)
        if teacher is None:
            continue
        available = total_slots - len(teacher.unavailable_slot_ids)
        daily_cap = teacher.max_periods_per_day * 5
        effective = min(available, daily_cap)
        if demand > effective:
            notes.append(
                f"{teacher.name} needs {demand} periods/week but only about "
                f"{effective} are available (availability + max {teacher.max_periods_per_day}/day)."
            )

    # Course-level demand vs timeslots (one class per slot)
    course_demand: dict[int, int] = defaultdict(int)
    for activity in schedule_input.activities:
        course_demand[activity.course_level_id] += activity.periods_per_week

    for course_level_id, demand in sorted(course_demand.items(), key=lambda x: -x[1]):
        course_level = schedule_input.course_levels_by_id.get(course_level_id)
        if course_level is None:
            continue
        shift = getattr(course_level, "shift", None)
        usable = sum(
            1 for ts in schedule_input.timeslots
            if timeslot_fits_shift(ts, shift)
        )
        if demand > usable:
            label = _course_level_label(course_level)
            notes.append(
                f"{label} needs {demand} periods/week but only "
                f"{usable} timeslots fit its {shift or 'DAY'} shift window."
            )

    # Global room/slot pressure
    if schedule_input.rooms and total_slots:
        capacity = total_slots * len(schedule_input.rooms)
        total_periods = sum(a.periods_per_week for a in schedule_input.activities)
        if total_periods > capacity:
            notes.append(
                f"Total demand is {total_periods} period-placements but only "
                f"{capacity} room×timeslot cells exist."
            )

    # Mention days with very few slots
    thin_days = [day for day, count in slots_per_day.items() if count <= 1]
    if thin_days and len(slots_per_day) >= 3:
        notes.append(
            "Some weekdays have very few active periods — check Timeslots."
        )

    return notes[:8]


def _suggestions(
    blocked: list[dict],
    top_reasons: list[dict],
    hard_constraint_notes: list[str],
    overload_notes: list[str],
) -> list[str]:
    tips: list[str] = []
    reason_text = " ".join(item["reason"].lower() for item in top_reasons)

    if "preferred" in reason_text:
        tips.append("Mark Preferred Teaching Time as soft, or widen the day/period window.")
    if "gap" in reason_text:
        tips.append("Mark No Adjacent Gaps as soft unless compact days are mandatory.")
    if "daily limit" in reason_text or "weekly limit" in reason_text:
        tips.append("Raise Max Daily/Weekly Periods, or reduce that teacher's assigned load.")
    if "unavailable" in reason_text:
        tips.append("Open more availability for the blocked teachers.")
    if "room type" in reason_text or "capacity" in reason_text:
        tips.append("Add matching rooms (type/capacity) or relax Room Type Required.")
    if "shift" in reason_text or any("shift window" in n.lower() for n in overload_notes):
        tips.append("Align course-level Morning/Day shift with active timeslots.")
    if overload_notes and not tips:
        tips.append("Reduce periods/week for overloaded teachers or course levels.")
    if hard_constraint_notes and len(hard_constraint_notes) >= 3:
        tips.append("Review hard constraints under Scheduling → Constraints; prefer soft rules when possible.")
    if blocked and not tips:
        tips.append("Open the listed example classes and check their teacher, shift, and room-type rules.")
    if not tips:
        tips.append("Try again after relaxing one hard constraint, or increase max restarts.")
    return tips


def _teacher_name(schedule_input: "ScheduleInput", teacher_id: int | None) -> str:
    if teacher_id is None:
        return "Unassigned teacher"
    teacher = schedule_input.teachers_by_id.get(teacher_id)
    return teacher.name if teacher else f"Teacher #{teacher_id}"


def _course_level_name(schedule_input: "ScheduleInput", course_level_id: int) -> str:
    course_level = schedule_input.course_levels_by_id.get(course_level_id)
    if course_level is None:
        return f"Course level #{course_level_id}"
    return _course_level_label(course_level)


def _course_level_label(course_level) -> str:
    code = getattr(course_level, "course_code", "") or ""
    name = getattr(course_level, "course_name", "") or ""
    level = getattr(course_level, "level", None)
    shift = getattr(course_level, "shift", None)
    parts = []
    if code:
        parts.append(code)
    elif name:
        parts.append(name)
    else:
        parts.append(getattr(course_level, "name", f"#{getattr(course_level, 'id', '?')}"))
    if level is not None:
        parts.append(f"Sem {level}")
    if name and code:
        parts.append(f"({name})")
    if shift:
        parts.append(f"{str(shift).title()} shift")
    return " · ".join(parts)


def describe_activity(activity: "ActivityData", schedule_input: "ScheduleInput") -> str:
    """One-line identity for a class session (course, semester, subject, teacher…)."""
    return _activity_detail(activity, schedule_input, reason="")["label"]


def _activity_detail(activity: "ActivityData", schedule_input: "ScheduleInput", reason: str) -> dict:
    course_level = schedule_input.course_levels_by_id.get(activity.course_level_id)
    course_code = getattr(activity, "course_code", "") or (
        getattr(course_level, "course_code", "") if course_level else ""
    )
    course_name = getattr(activity, "course_name", "") or (
        getattr(course_level, "course_name", "") if course_level else ""
    )
    semester = getattr(activity, "semester", None)
    if semester is None and course_level is not None:
        semester = course_level.level
    shift = getattr(activity, "shift", None) or (
        getattr(course_level, "shift", None) if course_level else None
    )
    subject_code = getattr(activity, "subject_code", "") or ""
    subject = activity.subject_name
    if subject_code:
        subject = f"{subject_code} — {subject}"

    teacher = _teacher_name(schedule_input, activity.teacher_id)
    room_req = activity.room_type_required or "any room type"

    identity_parts = []
    if course_code:
        identity_parts.append(course_code)
    if semester is not None:
        identity_parts.append(f"Sem {semester}")
    if course_name and course_code:
        identity_parts.append(course_name)
    elif course_name and not course_code:
        identity_parts.append(course_name)
    if shift:
        identity_parts.append(f"{str(shift).title()} shift")

    cohort = " · ".join(identity_parts) if identity_parts else _course_level_name(
        schedule_input, activity.course_level_id,
    )

    label = (
        f"{subject} | {cohort} | Teacher: {teacher} | "
        f"{activity.periods_per_week} period(s)/week | Room: {room_req}"
    )
    return {
        "activity_id": activity.id,
        "subject": subject,
        "subject_code": subject_code,
        "course_code": course_code,
        "course_name": course_name,
        "semester": semester,
        "shift": shift,
        "teacher": teacher,
        "course_level": cohort,
        "periods_per_week": activity.periods_per_week,
        "room_type_required": room_req,
        "label": label,
        "reason": reason,
    }


def _short_reason(message: str) -> str:
    if not message:
        return "Unknown blocker"
    # Keep the useful first clause for grouping.
    return message.split(";")[0].strip()
