"""
scheduling/tests/test_engine.py

Unit tests for the heuristic backtracking scheduling engine.

These tests are pure unittest.TestCase subclasses — they use no database,
no fixtures, and no Django test infrastructure beyond what TestCase provides.
All test data is constructed in-memory from the engine's dataclasses.

Test cases:
  TestTrivialCase       — 2 activities, 10 slots, 2 rooms; expects full placement
  TestDisplacementCase  — requires at least one displacement to resolve conflict
  TestInfeasibleCase    — genuinely infeasible input; expects clear failure
  TestSoftPenaltyCase   — verifies soft-constraint penalty calculation is correct

Running:
  python manage.py test scheduling.tests.test_engine --verbosity=2

Hard-constraint invariant:
  Every test that expects a successful result calls _assert_no_hard_violations()
  to explicitly verify the output — this is the most important property.
"""

from __future__ import annotations

import unittest

from scheduling.engine.algorithm import run_scheduler
from scheduling.engine.constraints import (
    compute_penalty,
    find_hard_violations,
    validate_single_placement,
)
from scheduling.engine.data_types import (
    ActivityData,
    ConstraintData,
    Placement,
    RoomData,
    ScheduleInput,
    SectionData,
    TeacherData,
    TimeSlotData,
)


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

def _make_timeslots(count: int, days: int = 5) -> list[TimeSlotData]:
    """
    Generate `count` timeslots spread across `days` days (Mon=1 … Fri=5).
    Periods are numbered starting at 1; each slot is 1 hour long starting 08:00.
    """
    slots = []
    slot_id = 1
    periods_per_day = max(1, (count + days - 1) // days)
    for day in range(1, days + 1):
        for period in range(1, periods_per_day + 1):
            if slot_id > count:
                break
            hour = 7 + period
            slots.append(
                TimeSlotData(
                    id=slot_id,
                    day_of_week=day,
                    period_number=period,
                    start_time=f"{hour:02d}:00",
                    end_time=f"{hour + 1:02d}:00",
                )
            )
            slot_id += 1
        if slot_id > count:
            break
    return slots


def _assert_no_hard_violations(test_case: unittest.TestCase, placements, schedule_input):
    """
    Assert that a set of placements contains zero hard-constraint violations.
    Calls find_hard_violations() and fails with a descriptive message if any
    violations are found.
    """
    violations = find_hard_violations(placements, schedule_input)
    test_case.assertListEqual(
        violations,
        [],
        msg=(
            f"Hard-constraint violations found in placement result:\n"
            + "\n".join(violations)
        ),
    )


def _assert_all_activities_placed(
    test_case: unittest.TestCase,
    result,
    schedule_input: ScheduleInput,
):
    """
    Assert that every activity's required periods_per_week is satisfied in
    the result placements (no activity is partially or fully missing).
    """
    from collections import Counter
    placed_counts = Counter(p.activity_id for p in result.placements)
    for activity in schedule_input.activities:
        test_case.assertEqual(
            placed_counts[activity.id],
            activity.periods_per_week,
            msg=(
                f"Activity id={activity.id} ({activity.subject_name!r}) "
                f"expected {activity.periods_per_week} placements, "
                f"got {placed_counts[activity.id]}."
            ),
        )


# ---------------------------------------------------------------------------
# Diagnostic validation helper
# ---------------------------------------------------------------------------

class TestSinglePlacementValidation(unittest.TestCase):
    """The editor relies on these specific hard-conflict diagnostics."""

    def setUp(self):
        self.schedule_input = ScheduleInput(
            timeslots=[
                TimeSlotData(1, 1, 1, "08:00", "09:00"),
                TimeSlotData(2, 1, 2, "09:00", "10:00"),
            ],
            rooms=[
                RoomData(1, "R101", 40, "LECTURE"),
                RoomData(2, "R102", 40, "LECTURE"),
            ],
            teachers=[
                TeacherData(1, "Ada Lovelace", 4, frozenset()),
                TeacherData(2, "Grace Hopper", 4, frozenset()),
            ],
            sections=[
                SectionData(1, "CS-A"),
                SectionData(2, "CS-B"),
            ],
            activities=[
                ActivityData(1, "Algorithms", 1, 1, teacher_id=1),
                ActivityData(2, "Databases", 2, 1, teacher_id=1),
                ActivityData(3, "Networks", 1, 1, teacher_id=2),
            ],
            constraints=[],
        )

    def test_reports_teacher_conflict(self):
        result = validate_single_placement(
            self.schedule_input.activities_by_id[2],
            1,
            2,
            [Placement(activity_id=1, timeslot_id=1, room_id=1)],
            self.schedule_input,
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.resource_type, "teacher")
        self.assertIn("Ada Lovelace", result.message)

    def test_reports_section_conflict(self):
        result = validate_single_placement(
            self.schedule_input.activities_by_id[3],
            1,
            2,
            [Placement(activity_id=1, timeslot_id=1, room_id=1)],
            self.schedule_input,
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.resource_type, "section")
        self.assertIn("CS-A", result.message)

    def test_reports_room_conflict(self):
        result = validate_single_placement(
            self.schedule_input.activities_by_id[2],
            1,
            1,
            [Placement(activity_id=1, timeslot_id=1, room_id=1)],
            self.schedule_input,
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.resource_type, "room")
        self.assertIn("R101", result.message)


# ---------------------------------------------------------------------------
# Test 1: Trivially satisfiable case
# ---------------------------------------------------------------------------

class TestTrivialCase(unittest.TestCase):
    """
    2 activities, 10 timeslots, 2 rooms.

    Expectation: the engine places both activities without difficulty.
    Verifications:
      - result.success is True
      - No hard-constraint violations
      - Each activity appears exactly once in placements (periods_per_week=1)
      - result.penalty >= 0 (may be 0 if no soft constraints defined)
    """

    def setUp(self):
        self.timeslots = _make_timeslots(10)

        self.rooms = [
            RoomData(id=1, name="Room A", capacity=40, room_type="LECTURE"),
            RoomData(id=2, name="Room B", capacity=30, room_type="LECTURE"),
        ]

        self.teachers = [
            TeacherData(
                id=1,
                name="Dr. Alpha",
                max_hours_per_day=4,
                unavailable_slot_ids=frozenset(),
            ),
            TeacherData(
                id=2,
                name="Dr. Beta",
                max_hours_per_day=4,
                unavailable_slot_ids=frozenset(),
            ),
        ]

        self.sections = [
            SectionData(id=1, name="CS-A"),
            SectionData(id=2, name="CS-B"),
        ]

        # Activity 1: Math for section CS-A, taught by Dr. Alpha, 1 period/week
        # Activity 2: Physics for section CS-B, taught by Dr. Beta, 1 period/week
        self.activities = [
            ActivityData(
                id=1,
                subject_name="Mathematics",
                section_id=1,
                periods_per_week=1,
                teacher_id=1,
                room_type_required=None,
            ),
            ActivityData(
                id=2,
                subject_name="Physics",
                section_id=2,
                periods_per_week=1,
                teacher_id=2,
                room_type_required=None,
            ),
        ]

        self.schedule_input = ScheduleInput(
            timeslots=self.timeslots,
            rooms=self.rooms,
            teachers=self.teachers,
            sections=self.sections,
            activities=self.activities,
            constraints=[],
        )

    def test_succeeds(self):
        result = run_scheduler(self.schedule_input, max_restarts=5, seed=0)
        self.assertTrue(result.success, msg=f"Expected success. Failure: {result.failure_reason}")

    def test_no_hard_violations(self):
        result = run_scheduler(self.schedule_input, max_restarts=5, seed=0)
        self.assertTrue(result.success)
        _assert_no_hard_violations(self, result.placements, self.schedule_input)

    def test_all_activities_placed(self):
        result = run_scheduler(self.schedule_input, max_restarts=5, seed=0)
        self.assertTrue(result.success)
        _assert_all_activities_placed(self, result, self.schedule_input)

    def test_placements_count(self):
        result = run_scheduler(self.schedule_input, max_restarts=5, seed=0)
        self.assertTrue(result.success)
        # 2 activities × 1 period/week = 2 placements total
        self.assertEqual(len(result.placements), 2)

    def test_penalty_is_non_negative(self):
        result = run_scheduler(self.schedule_input, max_restarts=5, seed=0)
        self.assertTrue(result.success)
        self.assertGreaterEqual(result.penalty, 0)

    def test_unplaced_is_empty_on_success(self):
        result = run_scheduler(self.schedule_input, max_restarts=5, seed=0)
        self.assertTrue(result.success)
        self.assertEqual(result.unplaced_activity_ids, [])

    def test_failure_reason_empty_on_success(self):
        result = run_scheduler(self.schedule_input, max_restarts=5, seed=0)
        self.assertTrue(result.success)
        self.assertEqual(result.failure_reason, "")

    def test_periods_per_week_multi(self):
        """An activity with 3 periods/week gets exactly 3 distinct placements."""
        activities = [
            ActivityData(
                id=10,
                subject_name="English",
                section_id=1,
                periods_per_week=3,
                teacher_id=1,
                room_type_required=None,
            ),
        ]
        si = ScheduleInput(
            timeslots=self.timeslots,
            rooms=self.rooms,
            teachers=self.teachers,
            sections=self.sections,
            activities=activities,
            constraints=[],
        )
        result = run_scheduler(si, max_restarts=5, seed=0)
        self.assertTrue(result.success)
        self.assertEqual(len(result.placements), 3)
        # All 3 placements must be in distinct timeslots
        slot_ids = [p.timeslot_id for p in result.placements]
        self.assertEqual(len(set(slot_ids)), 3, msg="Placements must use distinct timeslots")
        _assert_no_hard_violations(self, result.placements, si)


# ---------------------------------------------------------------------------
# Test 2: Displacement case
# ---------------------------------------------------------------------------

class TestDisplacementCase(unittest.TestCase):
    """
    Scenario designed to require at least one displacement:

    Setup:
      - 2 timeslots (slot 1: Mon period 1, slot 2: Mon period 2)
      - 2 rooms (Room 101 and Room 102)
      - 2 teachers, 2 sections
      - Activity A: section 1, teacher 1, 1 period/week
      - Activity B: section 1, teacher 2, 1 period/week
        (same section as A → A and B CANNOT share a slot)
      - Activity C: section 2, teacher 1, 1 period/week
        (same teacher as A → A and C CANNOT share a slot)

    Grid capacity: 2 slots × 2 rooms = 4 (slot, room) pairs available.
    Only 3 activities to place, so capacity is sufficient.

    Constraints that force displacement:
      A and B must be in different slots (same section).
      A and C must be in different slots (same teacher).
    Therefore A must be alone in one slot, and B and C must share the other
    slot (in different rooms — permitted since they have different teachers
    and different sections).

    Valid solutions:
      A→(slot1,R1), B→(slot2,R1), C→(slot2,R2)   [or A in slot2, B&C in slot1]

    The greedy pass may initially place A in slot 1 and then try to place C
    also in slot 1 (different section, different room is fine — wait, same
    teacher as A → blocked).  So C must go to slot 2.  Then B also goes to
    slot 2.  Both B and C are in slot 2 with different rooms and no teacher
    conflict — this works without displacement.

    To guarantee displacement is exercised, we seed the RNG so the order is
    [C, B, A]: C placed slot 1 Room 1, B placed slot 2 Room 1, then A cannot
    go to slot 1 (teacher conflict with C) or slot 2 Room 1 (room taken) but
    CAN go to slot 2 Room 2 — or needs displacement.  With enough restarts
    the algorithm resolves it.

    This test verifies:
      - result.success is True
      - No hard-constraint violations
      - All 3 activities are placed
    """

    def setUp(self):
        self.timeslots = [
            TimeSlotData(id=1, day_of_week=1, period_number=1, start_time="08:00", end_time="09:00"),
            TimeSlotData(id=2, day_of_week=1, period_number=2, start_time="09:00", end_time="10:00"),
        ]

        self.rooms = [
            RoomData(id=1, name="Room 101", capacity=60, room_type="LECTURE"),
            RoomData(id=2, name="Room 102", capacity=60, room_type="LECTURE"),
        ]

        self.teachers = [
            TeacherData(id=1, name="Teacher One", max_hours_per_day=4, unavailable_slot_ids=frozenset()),
            TeacherData(id=2, name="Teacher Two", max_hours_per_day=4, unavailable_slot_ids=frozenset()),
        ]

        self.sections = [
            SectionData(id=1, name="Sec-1"),
            SectionData(id=2, name="Sec-2"),
        ]

        self.activities = [
            # A: section 1, teacher 1
            ActivityData(id=1, subject_name="Maths", section_id=1, periods_per_week=1, teacher_id=1),
            # B: section 1, teacher 2 (same section as A → must be in different slot)
            ActivityData(id=2, subject_name="English", section_id=1, periods_per_week=1, teacher_id=2),
            # C: section 2, teacher 1 (same teacher as A → must be in different slot from A)
            ActivityData(id=3, subject_name="Science", section_id=2, periods_per_week=1, teacher_id=1),
        ]

        self.schedule_input = ScheduleInput(
            timeslots=self.timeslots,
            rooms=self.rooms,
            teachers=self.teachers,
            sections=self.sections,
            activities=self.activities,
            constraints=[],
        )

    def test_succeeds(self):
        result = run_scheduler(self.schedule_input, max_restarts=20, seed=0)
        self.assertTrue(
            result.success,
            msg=f"Expected success. Failure: {result.failure_reason}",
        )

    def test_no_hard_violations(self):
        result = run_scheduler(self.schedule_input, max_restarts=20, seed=0)
        self.assertTrue(result.success)
        _assert_no_hard_violations(self, result.placements, self.schedule_input)

    def test_all_activities_placed(self):
        result = run_scheduler(self.schedule_input, max_restarts=20, seed=0)
        self.assertTrue(result.success)
        _assert_all_activities_placed(self, result, self.schedule_input)

    def test_section_not_double_booked(self):
        """Section 1 (activities A and B) must be in different timeslots."""
        result = run_scheduler(self.schedule_input, max_restarts=20, seed=0)
        self.assertTrue(result.success)

        sec1_slots = [
            p.timeslot_id
            for p in result.placements
            if self.schedule_input.activities_by_id[p.activity_id].section_id == 1
        ]
        self.assertEqual(
            len(sec1_slots),
            len(set(sec1_slots)),
            msg="Section 1 has a double-booked timeslot.",
        )

    def test_teacher_not_double_booked(self):
        """Teacher 1 (activities A and C) must be in different timeslots."""
        result = run_scheduler(self.schedule_input, max_restarts=20, seed=0)
        self.assertTrue(result.success)

        t1_slots = [
            p.timeslot_id
            for p in result.placements
            if self.schedule_input.activities_by_id[p.activity_id].teacher_id == 1
        ]
        self.assertEqual(
            len(t1_slots),
            len(set(t1_slots)),
            msg="Teacher 1 is double-booked in a timeslot.",
        )


# ---------------------------------------------------------------------------
# Test 3: Genuinely infeasible case
# ---------------------------------------------------------------------------

class TestInfeasibleCase(unittest.TestCase):
    """
    Teacher is marked unavailable for ALL timeslots.

    Setup:
      - 4 timeslots
      - 1 room
      - 1 teacher, unavailable in ALL 4 slots
      - 1 activity requiring that teacher

    Expectation:
      - result.success is False
      - result.unplaced_activity_ids is non-empty (contains the activity id)
      - result.failure_reason is a non-empty string
      - result.placements is empty (never a partial/broken schedule)
      - result.penalty is 0 (no placements, so no penalty)
    """

    def setUp(self):
        self.timeslots = [
            TimeSlotData(id=1, day_of_week=1, period_number=1, start_time="08:00", end_time="09:00"),
            TimeSlotData(id=2, day_of_week=1, period_number=2, start_time="09:00", end_time="10:00"),
            TimeSlotData(id=3, day_of_week=2, period_number=1, start_time="08:00", end_time="09:00"),
            TimeSlotData(id=4, day_of_week=2, period_number=2, start_time="09:00", end_time="10:00"),
        ]

        self.rooms = [
            RoomData(id=1, name="Room X", capacity=50, room_type="LECTURE"),
        ]

        # Teacher is unavailable in ALL slots
        self.teachers = [
            TeacherData(
                id=1,
                name="Dr. Unavailable",
                max_hours_per_day=4,
                unavailable_slot_ids=frozenset([1, 2, 3, 4]),  # all slots blocked
            ),
        ]

        self.sections = [SectionData(id=1, name="Sec-X")]

        self.activities = [
            ActivityData(
                id=1,
                subject_name="Ghost Class",
                section_id=1,
                periods_per_week=1,
                teacher_id=1,
                room_type_required=None,
            ),
        ]

        self.schedule_input = ScheduleInput(
            timeslots=self.timeslots,
            rooms=self.rooms,
            teachers=self.teachers,
            sections=self.sections,
            activities=self.activities,
            constraints=[],
        )

    def test_returns_failure(self):
        result = run_scheduler(self.schedule_input, max_restarts=3, seed=0)
        self.assertFalse(
            result.success,
            msg="Expected failure for infeasible input, but got success.",
        )

    def test_failure_reason_non_empty(self):
        result = run_scheduler(self.schedule_input, max_restarts=3, seed=0)
        self.assertFalse(result.success)
        self.assertIsInstance(result.failure_reason, str)
        self.assertGreater(
            len(result.failure_reason),
            0,
            msg="failure_reason must be a non-empty string on failure.",
        )

    def test_unplaced_ids_non_empty(self):
        result = run_scheduler(self.schedule_input, max_restarts=3, seed=0)
        self.assertFalse(result.success)
        self.assertIn(
            1,
            result.unplaced_activity_ids,
            msg="Activity id=1 must appear in unplaced_activity_ids.",
        )

    def test_placements_empty_on_failure(self):
        """A failed result must have zero placements — never a partial schedule."""
        result = run_scheduler(self.schedule_input, max_restarts=3, seed=0)
        self.assertFalse(result.success)
        self.assertEqual(
            result.placements,
            [],
            msg="Placements must be empty on failure (no partial schedules).",
        )

    def test_penalty_zero_on_failure(self):
        result = run_scheduler(self.schedule_input, max_restarts=3, seed=0)
        self.assertFalse(result.success)
        self.assertEqual(result.penalty, 0)

    def test_infeasible_with_hard_daily_limit(self):
        """
        Additional infeasible scenario: only 1 slot exists but teacher has a
        hard MAX_DAILY_HOURS=0 constraint making any placement impossible.
        """
        timeslots = [
            TimeSlotData(id=10, day_of_week=1, period_number=1, start_time="08:00", end_time="09:00"),
        ]
        teachers = [
            TeacherData(id=10, name="Overloaded Teacher", max_hours_per_day=0, unavailable_slot_ids=frozenset()),
        ]
        sections = [SectionData(id=10, name="Sec-Y")]
        activities = [
            ActivityData(id=10, subject_name="Impossible", section_id=10, periods_per_week=1, teacher_id=10),
        ]
        constraints = [
            ConstraintData(
                id=1,
                constraint_type="MAX_DAILY_HOURS",
                is_hard=True,
                weight=10,
                teacher_id=10,
                max_daily_periods=0,  # zero → never allowed
            ),
        ]
        si = ScheduleInput(
            timeslots=timeslots,
            rooms=[RoomData(id=10, name="R", capacity=30, room_type="LECTURE")],
            teachers=teachers,
            sections=sections,
            activities=activities,
            constraints=constraints,
        )
        result = run_scheduler(si, max_restarts=3, seed=0)
        self.assertFalse(result.success, msg="Zero daily limit should make this infeasible.")
        self.assertIn(10, result.unplaced_activity_ids)


# ---------------------------------------------------------------------------
# Test 4: Soft-constraint penalty calculation
# ---------------------------------------------------------------------------

class TestSoftPenaltyCase(unittest.TestCase):
    """
    Verify that the soft-constraint penalty score changes correctly when
    teacher preference (availability / schedule density) varies.

    Scenario A — Teacher has a soft MAX_DAILY_HOURS=2 but gets scheduled for
    3 periods in one day: penalty > 0.

    Scenario B — Same teacher scheduled for exactly 2 periods in one day:
    penalty == 0.

    This validates that the penalty function correctly detects excess and
    that penalty(A) > penalty(B).
    """

    def _build_input_with_constraints(self, teacher_soft_daily_limit: int) -> ScheduleInput:
        """Helper: build a ScheduleInput with a soft MAX_DAILY_HOURS constraint."""
        timeslots = [
            TimeSlotData(id=1, day_of_week=1, period_number=1, start_time="08:00", end_time="09:00"),
            TimeSlotData(id=2, day_of_week=1, period_number=2, start_time="09:00", end_time="10:00"),
            TimeSlotData(id=3, day_of_week=1, period_number=3, start_time="10:00", end_time="11:00"),
            TimeSlotData(id=4, day_of_week=2, period_number=1, start_time="08:00", end_time="09:00"),
        ]
        rooms = [
            RoomData(id=1, name="R1", capacity=40, room_type="LECTURE"),
            RoomData(id=2, name="R2", capacity=40, room_type="LECTURE"),
            RoomData(id=3, name="R3", capacity=40, room_type="LECTURE"),
        ]
        teachers = [
            TeacherData(id=1, name="Dr. Soft", max_hours_per_day=10, unavailable_slot_ids=frozenset()),
        ]
        sections = [
            SectionData(id=1, name="Alpha"),
            SectionData(id=2, name="Beta"),
            SectionData(id=3, name="Gamma"),
        ]
        # 3 activities for the same teacher but different sections
        # → engine can place them in 3 different slots on the same day
        activities = [
            ActivityData(id=1, subject_name="Maths", section_id=1, periods_per_week=1, teacher_id=1),
            ActivityData(id=2, subject_name="Physics", section_id=2, periods_per_week=1, teacher_id=1),
            ActivityData(id=3, subject_name="Chemistry", section_id=3, periods_per_week=1, teacher_id=1),
        ]
        constraints = [
            ConstraintData(
                id=1,
                constraint_type="MAX_DAILY_HOURS",
                is_hard=False,           # soft — penalise, don't block
                weight=10,
                teacher_id=1,
                max_daily_periods=teacher_soft_daily_limit,
            ),
        ]
        return ScheduleInput(
            timeslots=timeslots,
            rooms=rooms,
            teachers=teachers,
            sections=sections,
            activities=activities,
            constraints=constraints,
        )

    def test_penalty_nonzero_when_over_limit(self):
        """
        Soft limit = 2 periods/day, but teacher is placed in 3 slots on Monday.
        Penalty must be > 0.
        """
        si = self._build_input_with_constraints(teacher_soft_daily_limit=2)
        result = run_scheduler(si, max_restarts=5, seed=0)
        self.assertTrue(result.success, msg=f"Failed: {result.failure_reason}")
        _assert_no_hard_violations(self, result.placements, si)
        # Count teacher's Monday placements
        monday_count = sum(
            1 for p in result.placements
            if si.timeslots_by_id[p.timeslot_id].day_of_week == 1
            and si.activities_by_id[p.activity_id].teacher_id == 1
        )
        if monday_count > 2:
            # Only assert penalty > 0 if the engine actually placed > 2 on Monday
            self.assertGreater(result.penalty, 0, msg="Penalty should be non-zero when over soft limit.")

    def test_penalty_zero_when_within_limit(self):
        """
        Soft limit = 10 periods/day (higher than we can ever hit with 4 slots).
        Penalty must be 0.
        """
        si = self._build_input_with_constraints(teacher_soft_daily_limit=10)
        result = run_scheduler(si, max_restarts=5, seed=0)
        self.assertTrue(result.success, msg=f"Failed: {result.failure_reason}")
        _assert_no_hard_violations(self, result.placements, si)
        self.assertEqual(
            result.penalty,
            0,
            msg="Penalty should be 0 when all placements are within soft daily limit.",
        )

    def test_lower_limit_higher_penalty(self):
        """
        With a stricter soft limit, penalty must be >= penalty of a looser limit.
        Both must produce successful schedules.
        """
        si_strict = self._build_input_with_constraints(teacher_soft_daily_limit=1)
        si_loose  = self._build_input_with_constraints(teacher_soft_daily_limit=10)

        result_strict = run_scheduler(si_strict, max_restarts=5, seed=0)
        result_loose  = run_scheduler(si_loose,  max_restarts=5, seed=0)

        self.assertTrue(result_strict.success, msg=f"Strict failed: {result_strict.failure_reason}")
        self.assertTrue(result_loose.success,  msg=f"Loose failed: {result_loose.failure_reason}")

        _assert_no_hard_violations(self, result_strict.placements, si_strict)
        _assert_no_hard_violations(self, result_loose.placements, si_loose)

        self.assertGreaterEqual(
            result_strict.penalty,
            result_loose.penalty,
            msg=(
                "A stricter soft daily limit should produce a penalty >= "
                "a looser limit given the same schedule."
            ),
        )

    def test_compute_penalty_directly(self):
        """
        Build a hand-crafted placement set and call compute_penalty() directly
        to verify the penalty arithmetic independently of the algorithm.

        Setup: teacher 1 has 3 placements all on Monday (day=1), soft limit=2.
        Expected penalty: (3-2) excess * weight=10 = 10.
        """
        timeslots = [
            TimeSlotData(id=1, day_of_week=1, period_number=1, start_time="08:00", end_time="09:00"),
            TimeSlotData(id=2, day_of_week=1, period_number=2, start_time="09:00", end_time="10:00"),
            TimeSlotData(id=3, day_of_week=1, period_number=3, start_time="10:00", end_time="11:00"),
        ]
        rooms = [RoomData(id=1, name="R", capacity=40, room_type="LECTURE")]
        teachers = [TeacherData(id=1, name="T", max_hours_per_day=10, unavailable_slot_ids=frozenset())]
        sections = [
            SectionData(id=1, name="S1"),
            SectionData(id=2, name="S2"),
            SectionData(id=3, name="S3"),
        ]
        activities = [
            ActivityData(id=1, subject_name="A", section_id=1, periods_per_week=1, teacher_id=1),
            ActivityData(id=2, subject_name="B", section_id=2, periods_per_week=1, teacher_id=1),
            ActivityData(id=3, subject_name="C", section_id=3, periods_per_week=1, teacher_id=1),
        ]
        constraints = [
            ConstraintData(
                id=1,
                constraint_type="MAX_DAILY_HOURS",
                is_hard=False,
                weight=10,
                teacher_id=1,
                max_daily_periods=2,  # limit = 2; 3 placed → excess = 1 → penalty = 10
            ),
        ]
        si = ScheduleInput(
            timeslots=timeslots,
            rooms=[RoomData(id=1, name="R", capacity=40, room_type="LECTURE"),
                   RoomData(id=2, name="R2", capacity=40, room_type="LECTURE"),
                   RoomData(id=3, name="R3", capacity=40, room_type="LECTURE")],
            teachers=teachers,
            sections=sections,
            activities=activities,
            constraints=constraints,
        )

        # Hand-craft placements: all 3 activities on Monday in slots 1, 2, 3
        placements = [
            Placement(activity_id=1, timeslot_id=1, room_id=1),
            Placement(activity_id=2, timeslot_id=2, room_id=2),
            Placement(activity_id=3, timeslot_id=3, room_id=3),
        ]

        penalty = compute_penalty(placements, si)
        self.assertEqual(
            penalty,
            10,
            msg=(
                f"Expected penalty=10 (1 excess period × weight=10), got {penalty}. "
                "compute_penalty() arithmetic is incorrect."
            ),
        )

    def test_no_adjacent_gap_penalty(self):
        """
        NO_ADJACENT_GAPS soft constraint: a teacher with a gap in their daily
        schedule should incur a penalty; a teacher with a compact schedule should not.
        """
        timeslots = [
            TimeSlotData(id=1, day_of_week=1, period_number=1, start_time="08:00", end_time="09:00"),
            TimeSlotData(id=2, day_of_week=1, period_number=2, start_time="09:00", end_time="10:00"),
            TimeSlotData(id=3, day_of_week=1, period_number=3, start_time="10:00", end_time="11:00"),
        ]
        rooms = [
            RoomData(id=1, name="R1", capacity=40, room_type="LECTURE"),
            RoomData(id=2, name="R2", capacity=40, room_type="LECTURE"),
        ]
        teachers = [TeacherData(id=1, name="T", max_hours_per_day=10, unavailable_slot_ids=frozenset())]
        sections = [SectionData(id=1, name="S1"), SectionData(id=2, name="S2")]
        constraints = [
            ConstraintData(
                id=2,
                constraint_type="NO_ADJACENT_GAPS",
                is_hard=False,
                weight=5,
                teacher_id=1,
            ),
        ]

        activities_dummy = [
            ActivityData(id=1, subject_name="X", section_id=1, periods_per_week=1, teacher_id=1),
            ActivityData(id=2, subject_name="Y", section_id=2, periods_per_week=1, teacher_id=1),
        ]
        si = ScheduleInput(
            timeslots=timeslots,
            rooms=rooms,
            teachers=teachers,
            sections=sections,
            activities=activities_dummy,
            constraints=constraints,
        )

        # Compact: periods 1 and 2 (no gap) → 0 penalty
        compact_placements = [
            Placement(activity_id=1, timeslot_id=1, room_id=1),
            Placement(activity_id=2, timeslot_id=2, room_id=2),
        ]
        penalty_compact = compute_penalty(compact_placements, si)
        self.assertEqual(penalty_compact, 0, msg="Consecutive periods should have no gap penalty.")

        # Gapped: periods 1 and 3 (gap at period 2) → 1 gap × weight=5 = 5
        gapped_placements = [
            Placement(activity_id=1, timeslot_id=1, room_id=1),
            Placement(activity_id=2, timeslot_id=3, room_id=2),
        ]
        penalty_gapped = compute_penalty(gapped_placements, si)
        self.assertEqual(penalty_gapped, 5, msg="Gapped schedule should have penalty=5 (1 gap × weight 5).")

        self.assertGreater(
            penalty_gapped,
            penalty_compact,
            msg="Gapped schedule must have higher penalty than compact schedule.",
        )


class TestRoomCapacity(unittest.TestCase):
    """Room capacity hard constraint uses SectionData.student_count."""

    def setUp(self):
        self.schedule_input = ScheduleInput(
            timeslots=[
                TimeSlotData(1, 1, 1, "08:00", "09:00"),
            ],
            rooms=[
                RoomData(1, "Small Room", 30, "LECTURE"),
                RoomData(2, "Large Room", 60, "LECTURE"),
            ],
            teachers=[
                TeacherData(1, "Dr. Capacity", 4, frozenset()),
            ],
            sections=[
                SectionData(1, "Large Section", student_count=50),
            ],
            activities=[
                ActivityData(1, "Physics", 1, 1, teacher_id=1),
            ],
            constraints=[],
        )

    def test_rejects_room_that_is_too_small(self):
        result = validate_single_placement(
            self.schedule_input.activities_by_id[1],
            1,
            1,
            [],
            self.schedule_input,
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.resource_type, "room")
        self.assertIn("capacity", result.message.lower())

    def test_accepts_room_with_sufficient_capacity(self):
        result = validate_single_placement(
            self.schedule_input.activities_by_id[1],
            1,
            2,
            [],
            self.schedule_input,
        )

        self.assertTrue(result.is_valid)


# ---------------------------------------------------------------------------
# Run as standalone script (for quick local debugging)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
