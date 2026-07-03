"""
scheduling/engine/algorithm.py

Heuristic backtracking scheduling algorithm — §3.4.1 of the TimeForge proposal.

Algorithm overview (Shuffle → Place → Displace-and-retry → Restart-with-new-seed):

  For up to `max_restarts` attempts:
    1. Shuffle the expanded activity list using the current random seed.
    2. For each activity slot-requirement (one item per periods_per_week):
       a. Collect every (timeslot, room) pair that passes all hard constraints.
       b. If any found → make a greedy placement (smallest-capacity valid room,
          lowest-period timeslot to keep schedules compact).
       c. If none found → enter displacement phase:
            - Find an already-placed activity whose placement is blocking ours.
            - Temporarily pull it from the schedule.
            - Re-test the original activity — if it can now be placed, do so.
            - Try to re-place the displaced activity elsewhere.
            - If the displaced activity cannot be re-placed, undo both and
              count this as a failed displacement attempt.
          Each activity gets at most `retry_threshold` displacement attempts
          before we abandon this restart.
    3. If all items are placed → run the hard-constraint audit (safety gate)
       → compute soft penalty → return ScheduleResult(success=True).
    4. If items remain unplaced after the retry loop → increment seed →
       try the next restart.

  After all restarts exhausted without success:
    → return ScheduleResult(success=False, unplaced_activity_ids=[…])

Design rules:
  - No Django imports — this file must be importable without Django configured.
  - Displacement is shallow (depth=1): we displace one conflicting placement,
    not chains.  This matches §3.4.1 and avoids infinite recursion.
  - Room assignment is greedy smallest-fit: among valid rooms, pick the one
    with the smallest capacity that still fits the section, to leave larger
    rooms for activities that need them.
  - Before returning success, the hard-constraint audit is called;
    an internal bug that violates a hard constraint raises AssertionError
    rather than silently returning a broken schedule.
"""

from __future__ import annotations

import logging
import random
from typing import Optional

from .constraints import (
    compute_penalty,
    find_hard_violations,
    is_hard_feasible,
)
from .data_types import (
    ActivityData,
    Placement,
    ScheduleInput,
    ScheduleResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_scheduler(
    schedule_input: ScheduleInput,
    max_restarts: int = 10,
    retry_threshold: int = 20,
    seed: Optional[int] = None,
) -> ScheduleResult:
    """
    Run the heuristic backtracking scheduler.

    Parameters
    ----------
    schedule_input : ScheduleInput
        All data required for the run (activities, rooms, timeslots, etc.).
    max_restarts : int
        Maximum number of full restarts with a new random seed before
        declaring the problem infeasible.  Default: 10.
    retry_threshold : int
        Maximum number of displacement attempts per activity per restart
        before giving up on that restart.  Default: 20.
    seed : int, optional
        Starting random seed.  If None, a fixed default is used so that
        a zero-argument call is still deterministic for testing.

    Returns
    -------
    ScheduleResult
        success=True  → placements is complete and hard-constraint-clean.
        success=False → failure_reason and unplaced_activity_ids explain why.
    """
    if seed is None:
        seed = 42  # deterministic default; callers can pass None for randomness

    # Expand activities: one item per required period slot
    expanded = _expand_activities(schedule_input.activities)

    if not expanded:
        # No activities to schedule — trivially successful
        return ScheduleResult(
            success=True,
            placements=[],
            penalty=0,
            unplaced_activity_ids=[],
            failure_reason="",
        )

    if not schedule_input.timeslots:
        return ScheduleResult(
            success=False,
            placements=[],
            penalty=0,
            unplaced_activity_ids=[a.id for a in schedule_input.activities],
            failure_reason="No timeslots available in the schedule input.",
        )

    if not schedule_input.rooms:
        return ScheduleResult(
            success=False,
            placements=[],
            penalty=0,
            unplaced_activity_ids=[a.id for a in schedule_input.activities],
            failure_reason="No rooms available in the schedule input.",
        )

    rng = random.Random(seed)

    for restart_num in range(max_restarts):
        logger.debug("Scheduler restart %d/%d (seed=%d)", restart_num + 1, max_restarts, seed)

        shuffled = list(expanded)
        rng.shuffle(shuffled)

        result = _attempt_placement(
            shuffled,
            schedule_input,
            retry_threshold,
            rng,
        )

        if result is not None:
            # Safety gate: verify no hard violations before declaring success
            violations = find_hard_violations(result, schedule_input)
            assert not violations, (
                "BUG: engine produced hard-constraint violations on a claimed-success result.\n"
                + "\n".join(violations)
            )
            penalty = compute_penalty(result, schedule_input)
            logger.debug(
                "Scheduler succeeded on restart %d with %d placements, penalty=%d",
                restart_num + 1,
                len(result),
                penalty,
            )
            return ScheduleResult(
                success=True,
                placements=result,
                penalty=penalty,
                unplaced_activity_ids=[],
                failure_reason="",
            )

        # Prepare for next restart
        seed += 1
        rng = random.Random(seed)
        logger.debug("Restart %d failed, trying new seed %d", restart_num + 1, seed)

    # All restarts exhausted
    unplaced_ids = _collect_unplaced_ids(expanded, schedule_input)
    return ScheduleResult(
        success=False,
        placements=[],
        penalty=0,
        unplaced_activity_ids=unplaced_ids,
        failure_reason=(
            f"Could not place all activities after {max_restarts} restart(s). "
            f"Unplaceable activity IDs: {unplaced_ids}. "
            "Check teacher unavailability, room availability, and constraint settings."
        ),
    )


# ---------------------------------------------------------------------------
# One placement attempt (one restart)
# ---------------------------------------------------------------------------

def _attempt_placement(
    shuffled_items: list[tuple[ActivityData, int]],
    schedule_input: ScheduleInput,
    retry_threshold: int,
    rng: random.Random,
) -> Optional[list[Placement]]:
    """
    Try to place every item in `shuffled_items` using greedy placement with
    shallow displacement.

    Returns a complete list of Placement objects on success, or None if any
    item could not be placed within `retry_threshold` displacement attempts.
    """
    placements: list[Placement] = []

    for activity, _period_index in shuffled_items:
        placed = _try_place_one(
            activity,
            placements,
            schedule_input,
            retry_threshold,
            rng,
        )
        if not placed:
            return None  # This restart is a failure

    return placements


def _try_place_one(
    activity: ActivityData,
    placements: list[Placement],
    schedule_input: ScheduleInput,
    retry_threshold: int,
    rng: random.Random,
) -> bool:
    """
    Try to place `activity` somewhere in the timetable.

    First attempts direct greedy placement; if that fails, attempts shallow
    displacement up to `retry_threshold` times.

    Returns True if the activity was placed (placements is mutated),
    False if no placement could be found within the retry budget.
    """
    # Direct greedy placement
    candidate = _find_best_slot(activity, placements, schedule_input)
    if candidate is not None:
        placements.append(candidate)
        return True

    # Displacement phase: try up to retry_threshold times
    for attempt in range(retry_threshold):
        displaced_idx = _find_displaceable(activity, placements, schedule_input, rng)
        if displaced_idx is None:
            # No displaceable activity found — give up
            break

        # Temporarily remove the conflicting placement
        displaced = placements.pop(displaced_idx)
        displaced_activity = schedule_input.activities_by_id[displaced.activity_id]

        # Try to place the original activity now
        candidate = _find_best_slot(activity, placements, schedule_input)
        if candidate is not None:
            placements.append(candidate)
            # Try to re-place the displaced activity
            re_placed = _find_best_slot(displaced_activity, placements, schedule_input)
            if re_placed is not None:
                placements.append(re_placed)
                return True
            else:
                # Can't re-place displaced activity — undo both
                placements.remove(candidate)

        # Restore the displaced placement and try a different one
        placements.insert(displaced_idx, displaced)

    return False


# ---------------------------------------------------------------------------
# Greedy placement helpers
# ---------------------------------------------------------------------------

def _find_best_slot(
    activity: ActivityData,
    existing_placements: list[Placement],
    schedule_input: ScheduleInput,
) -> Optional[Placement]:
    """
    Find the best available (timeslot, room) pair for `activity`.

    "Best" is defined as:
      - Primary sort: lowest day_of_week (compact schedule)
      - Secondary sort: lowest period_number (early in day)
      - Room: smallest-capacity valid room (greedy smallest-fit)

    Returns a Placement if found, None if no valid slot exists.
    """
    # Sort timeslots: day first, then period (keeps schedule compact)
    sorted_slots = sorted(
        schedule_input.timeslots,
        key=lambda ts: (ts.day_of_week, ts.period_number),
    )

    # Sort rooms: smallest capacity first (greedy smallest-fit)
    sorted_rooms = sorted(
        schedule_input.rooms,
        key=lambda r: r.capacity,
    )

    # Avoid placing the same activity in the same timeslot it already occupies
    # (an activity with periods_per_week > 1 gets multiple Placement records,
    #  but each must be in a distinct timeslot)
    already_used_slots = {
        p.timeslot_id
        for p in existing_placements
        if p.activity_id == activity.id
    }

    for ts in sorted_slots:
        if ts.id in already_used_slots:
            continue
        for room in sorted_rooms:
            if is_hard_feasible(activity, ts.id, room.id, existing_placements, schedule_input):
                return Placement(
                    activity_id=activity.id,
                    timeslot_id=ts.id,
                    room_id=room.id,
                )

    return None


def _find_displaceable(
    target_activity: ActivityData,
    placements: list[Placement],
    schedule_input: ScheduleInput,
    rng: random.Random,
) -> Optional[int]:
    """
    Find the index of a placed activity that is blocking `target_activity`.

    A placement is "blocking" if removing it would cause at least one
    hard constraint that was previously violated to no longer be violated
    when attempting to place `target_activity`.

    We shuffle the candidate list to avoid deterministic cycling that could
    prevent convergence across restarts.

    Returns the index in `placements`, or None if nothing is displaceable.
    """
    # Find slots where target_activity has a conflict
    candidate_indices = []

    for i, p in enumerate(placements):
        placed_act = schedule_input.activities_by_id.get(p.activity_id)
        if placed_act is None:
            continue

        # Is this placement in a slot where target_activity could potentially go?
        # We check if removing it would free up something for target_activity.
        # Heuristic: any placement that shares a teacher, section, or is simply
        # occupying a slot the target_activity might want.
        slot = schedule_input.timeslots_by_id.get(p.timeslot_id)
        if slot is None:
            continue

        is_candidate = False

        # Same teacher conflict
        if (
            target_activity.teacher_id is not None
            and placed_act.teacher_id == target_activity.teacher_id
        ):
            is_candidate = True

        # Same section conflict (section double-booking)
        if placed_act.section_id == target_activity.section_id:
            is_candidate = True

        # Same room type needed — removing might free a compatible room in that slot
        if (
            target_activity.room_type_required is not None
            and placed_act.room_type_required == target_activity.room_type_required
        ):
            is_candidate = True

        if is_candidate:
            candidate_indices.append(i)

    if not candidate_indices:
        return None

    rng.shuffle(candidate_indices)
    return candidate_indices[0]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _expand_activities(activities: list[ActivityData]) -> list[tuple[ActivityData, int]]:
    """
    Expand the activity list: for an activity with periods_per_week=3, produce
    3 tuples [(activity, 0), (activity, 1), (activity, 2)].

    The second element is just an index to distinguish the duplicates; the
    algorithm places each as a separate (activity, timeslot, room) Placement.
    """
    expanded = []
    for activity in activities:
        for period_index in range(activity.periods_per_week):
            expanded.append((activity, period_index))
    return expanded


def _collect_unplaced_ids(
    expanded_items: list[tuple[ActivityData, int]],
    schedule_input: ScheduleInput,
) -> list[int]:
    """
    Return the distinct activity IDs from activities that could not be placed.

    This is called only in the failure path — we reconstruct from the expanded
    list rather than trying to figure out which placements succeeded, because
    in the failure path `placements` has already been discarded.
    """
    # All activities are unplaced (we return [] for success; this is failure path)
    seen = set()
    unplaced = []
    for activity, _ in expanded_items:
        if activity.id not in seen:
            seen.add(activity.id)
            unplaced.append(activity.id)
    return unplaced
