"""
scheduling/engine/data_types.py

Pure-Python dataclasses for the scheduling engine's internal representation.
These mirror the Django models but carry ZERO Django dependency — they are
plain data containers that can be constructed in unit tests without a database.

Mapping to DB models (for maintainers):
  RoomData        ← core.Room
  TeacherData     ← academics.TeacherProfile + scheduling.TeacherAvailability
  SectionData     ← academics.Section
  ActivityData    ← academics.ClassSession
  TimeSlotData    ← scheduling.TimeSlot
  ConstraintData  ← scheduling.Constraint
  ScheduleInput   ← all of the above, assembled for one semester
  Placement       ← one (activity, timeslot, room) assignment (unsaved result)
  ScheduleResult  ← the engine's full output
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Resource descriptors
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RoomData:
    """A physical room the engine may assign to a class session."""
    id: int
    name: str
    capacity: int
    room_type: str          # matches core.Room.RoomType values: LECTURE, LAB, etc.


@dataclass(frozen=True)
class TeacherData:
    """A teacher with their hard unavailability set."""
    id: int
    name: str
    max_hours_per_day: int                      # maximum periods per calendar day
    unavailable_slot_ids: frozenset             # set of TimeSlotData.id the teacher cannot teach


@dataclass(frozen=True)
class SectionData:
    """A student section/cohort."""
    id: int
    name: str


@dataclass(frozen=True)
class TimeSlotData:
    """One atomic period in the weekly grid."""
    id: int
    day_of_week: int        # 1=Monday … 5=Friday (matches TimeSlot.DayOfWeek)
    period_number: int
    start_time: str         # HH:MM string — keeps the dataclass stdlib-only
    end_time: str           # HH:MM string


@dataclass(frozen=True)
class ActivityData:
    """
    One schedulable unit derived from a ClassSession.

    periods_per_week means the engine must assign this activity to exactly
    `periods_per_week` distinct TimeSlots across the week (one placement per
    required period).  Each such placement is a separate Placement record in
    the result.

    Example: English (3 periods/week) → 3 Placement records with the same
    activity_id but different timeslot_ids.
    """
    id: int
    subject_name: str
    section_id: int
    periods_per_week: int
    teacher_id: Optional[int] = None           # None → no teacher assigned yet (unassigned)
    room_type_required: Optional[str] = None   # None → any room type is acceptable


# ---------------------------------------------------------------------------
# Constraint descriptor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConstraintData:
    """
    A single constraint record from scheduling.Constraint.

    Hard constraints (is_hard=True) are enforced as absolute filters; the
    engine will never produce a placement that violates them.

    Soft constraints (is_hard=False) incur a `weight` penalty per violation
    and contribute to the final ScheduleResult.penalty score.

    constraint_type values that the engine understands:
      MAX_DAILY_HOURS  — uses max_daily_periods
      NO_ADJACENT_GAPS — soft: penalises gaps in a teacher's or section's day
      ROOM_TYPE_REQUIRED — enforced via ActivityData.room_type_required (hard)
      CUSTOM — ignored by engine (passed through, not evaluated)
    """
    id: int
    constraint_type: str
    is_hard: bool
    weight: int                         # penalty per violation for soft constraints
    teacher_id: Optional[int] = None    # None → applies globally or to non-teacher scope
    section_id: Optional[int] = None
    max_daily_periods: Optional[int] = None


# ---------------------------------------------------------------------------
# Bundled input
# ---------------------------------------------------------------------------

@dataclass
class ScheduleInput:
    """
    All data the engine needs for one scheduling run, assembled by models_io.py.

    The engine never queries the database; it only reads from this object.
    """
    timeslots: list                  # list[TimeSlotData], sorted by day then period
    rooms: list                      # list[RoomData]
    teachers: list                   # list[TeacherData]
    sections: list                   # list[SectionData]
    activities: list                 # list[ActivityData]
    constraints: list                # list[ConstraintData]

    # Convenience look-up dicts — populated by __post_init__
    timeslots_by_id: dict = field(default_factory=dict, init=False)
    rooms_by_id: dict = field(default_factory=dict, init=False)
    teachers_by_id: dict = field(default_factory=dict, init=False)
    sections_by_id: dict = field(default_factory=dict, init=False)
    activities_by_id: dict = field(default_factory=dict, init=False)

    def __post_init__(self):
        self.timeslots_by_id = {ts.id: ts for ts in self.timeslots}
        self.rooms_by_id = {r.id: r for r in self.rooms}
        self.teachers_by_id = {t.id: t for t in self.teachers}
        self.sections_by_id = {s.id: s for s in self.sections}
        self.activities_by_id = {a.id: a for a in self.activities}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class Placement:
    """
    One (activity, timeslot, room) assignment produced by the engine.

    If an activity has periods_per_week=3, the result will contain 3 Placement
    records all with the same activity_id but different timeslot_ids.
    """
    activity_id: int
    timeslot_id: int
    room_id: int


@dataclass
class ScheduleResult:
    """
    The complete output of a scheduling run.

    On success  → success=True,  placements is fully populated, penalty≥0.
    On failure  → success=False, placements is empty (never partial/broken),
                  unplaced_activity_ids lists every activity that could not be
                  placed, failure_reason explains why.
    """
    success: bool
    placements: list            # list[Placement] — empty on failure
    penalty: int                # soft-constraint total; 0 on failure
    unplaced_activity_ids: list # list[int] — empty on success
    failure_reason: str = ""    # human-readable; empty on success
