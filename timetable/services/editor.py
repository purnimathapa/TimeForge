"""Batch editor helpers for hypothetical placement validation."""

from __future__ import annotations

from scheduling.engine.data_types import Placement
from scheduling.models import TimeSlot
from timetable.models import Timetable, TimetableSlot


class MoveParseError(Exception):
    """Raised when a batch move payload cannot be parsed."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def parse_move_payloads(moves_raw) -> list[dict]:
    """Parse and normalise move dicts from a JSON batch request."""
    if not isinstance(moves_raw, list):
        raise MoveParseError('moves must be a list.')

    parsed: list[dict] = []
    seen_slot_ids: set[int] = set()

    for index, move in enumerate(moves_raw):
        if not isinstance(move, dict):
            raise MoveParseError(f'Move at index {index} must be an object.')

        slot_id = move.get('slot_id')
        target_day = move.get('target_day')
        target_period = move.get('target_period')
        target_room = move.get('target_room')

        if not all([slot_id, target_day, target_period, target_room]):
            raise MoveParseError(
                'Each move must include slot_id, target_day, target_period, and target_room.',
            )

        try:
            slot_id = int(slot_id)
            target_day = int(target_day)
            target_period = int(target_period)
            target_room = int(target_room)
        except (TypeError, ValueError) as exc:
            raise MoveParseError('Move target values must be numeric.') from exc

        if slot_id in seen_slot_ids:
            raise MoveParseError(f'Duplicate slot_id {slot_id} in batch.')

        seen_slot_ids.add(slot_id)
        target_timeslot = resolve_target_timeslot(target_day, target_period)
        parsed.append({
            'slot_id': slot_id,
            'target_timeslot': target_timeslot,
            'target_room_id': target_room,
        })

    return parsed


def resolve_target_timeslot(target_day: int, target_period: int) -> TimeSlot:
    try:
        return TimeSlot.objects.get(
            day_of_week=target_day,
            period_number=target_period,
            is_active=True,
        )
    except TimeSlot.DoesNotExist as exc:
        raise MoveParseError('Target period is not active.') from exc


def build_hypothetical_placements(timetable: Timetable, move_payloads: list[dict]) -> list[Placement]:
    """
    Build engine Placement objects for a timetable with proposed moves applied in memory.

    Slots not listed in move_payloads keep their committed timeslot and room.
    """
    moves_by_slot = {move['slot_id']: move for move in move_payloads}
    slot_ids_in_moves = set(moves_by_slot)

    slots = list(
        TimetableSlot.objects.filter(timetable=timetable)
        .select_related('class_session', 'timeslot', 'room')
    )
    slot_map = {slot.pk: slot for slot in slots}

    unknown_ids = slot_ids_in_moves - set(slot_map)
    if unknown_ids:
        raise MoveParseError(
            f'Slot id(s) {sorted(unknown_ids)} do not belong to timetable {timetable.pk}.',
        )

    placements: list[Placement] = []
    for slot in slots:
        if slot.pk in moves_by_slot:
            move = moves_by_slot[slot.pk]
            placements.append(
                Placement(
                    activity_id=slot.class_session_id,
                    timeslot_id=move['target_timeslot'].id,
                    room_id=move['target_room_id'],
                )
            )
        else:
            placements.append(
                Placement(
                    activity_id=slot.class_session_id,
                    timeslot_id=slot.timeslot_id,
                    room_id=slot.room_id,
                )
            )

    return placements
