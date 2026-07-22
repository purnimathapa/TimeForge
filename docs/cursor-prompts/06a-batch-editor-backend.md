# PROMPT 06A — Batch Editor Backend (Stage → Validate → Publish Moves)

Paste this entire file into Cursor Agent mode.

**Do not start 06B until 06A is merged, migrated, and tests pass.**

---

## Goal

Replace immediate-save drag-and-drop with **server-side draft change sets** and batch validation. **No frontend changes in this prompt** except minimal URL wiring if needed.

## Prerequisites

Prompt 05 complete.

## Current problem

`MoveSlotView` validates and saves **one move per drop**. `validate_single_placement()` cannot catch conflicts between two pending moves. v2 requires batch check before commit.

## Tasks

### 1. Models — `timetable/models.py`

Add:

```python
class DraftChangeSet(models.Model):
    timetable = models.ForeignKey(Timetable, on_delete=models.CASCADE, related_name='draft_change_sets')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    is_valid = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)
    is_discarded = models.BooleanField(default=False)

class DraftMove(models.Model):
    change_set = models.ForeignKey(DraftChangeSet, on_delete=models.CASCADE, related_name='moves')
    slot = models.ForeignKey(TimetableSlot, on_delete=models.CASCADE, related_name='draft_moves')
    target_timeslot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE)
    target_room = models.ForeignKey(Room, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('change_set', 'slot')]
```

Run migrations.

### 2. Helper — build hypothetical placements

In `timetable/views.py` (or `timetable/services/editor.py` if you prefer — one new small module is OK):

Function that takes a timetable + list of move dicts, returns list of `Placement` dataclasses reflecting **committed slots with all proposed moves applied in memory**.

Reuse `_slots_to_placements()` and logic from existing `MoveSlotView`.

### 3. `ValidateBatchView` — POST JSON, admin-only

Path: `slots/validate-batch/`, name `validate_batch`

Body:
```json
{"timetable_id": 1, "moves": [{"slot_id": 1, "target_day": 1, "target_period": 2, "target_room": 3}, ...]}
```

Steps:
1. Load `schedule_input = load_schedule_input(timetable.semester_id)`
2. Build hypothetical `Placement` list
3. Call `find_hard_violations(placements, schedule_input)` from `scheduling/engine/constraints.py`
4. Call `compute_penalty(placements, schedule_input)`
5. Upsert `DraftChangeSet` + replace `DraftMove` rows for this user/timetable (unpublished, undiscarded)
6. Set `is_valid = (violations == [])`, `last_checked_at = now`
7. Return JSON: `{ok, is_valid, violations, penalty_score, change_set_id}`

**Do not use `validate_single_placement()` for the batch** — wrong tool.

### 4. `PublishChangeSetView` — POST JSON, admin-only

Path: `change-sets/publish/`, name `publish_change_set`

Body: `{"change_set_id": 1}`

- Refuse if not `is_valid`, or already published/discarded
- In **one** `transaction.atomic()`: apply each DraftMove to TimetableSlot (same field updates as current `MoveSlotView`: timeslot, room, teacher from class_session, `is_locked=True`, `is_manual=True`)
- Recompute `penalty_score` **once** on timetable
- Set `change_set.is_published = True`
- Return updated summary JSON

### 5. `DiscardChangeSetView` — POST JSON, admin-only

Path: `change-sets/discard/`, name `discard_change_set`

- Mark discarded; delete DraftMove rows (or keep — document choice)
- **No** TimetableSlot changes

### 6. Keep `MoveSlotView` for now

Do **not** remove yet — 06B frontend will stop calling it. Optionally add comment "deprecated after batch editor".

Wire URLs in `timetable/urls.py`.

## Out of scope

- JavaScript / SortableJS (Prompt 06B)
- Timetable DRAFT→PUBLISHED workflow (Prompt 07)
- Changing `scheduling/engine/algorithm.py`

## Tests — `timetable/tests.py`

1. Validate empty moves → valid, penalty computed
2. **Critical:** Two moves individually valid but together violate teacher double-booking → batch `is_valid: false`
3. Publish after valid check → slots updated atomically
4. Discard → no slot changes
5. Publish without valid check → 400
6. Teacher POST to validate/publish → 403

## Acceptance criteria

- [ ] Migrations apply
- [ ] Batch validation catches combined conflict
- [ ] Publish applies all moves in one transaction
- [ ] All tests pass

## Git commit message

```
feat: batch timetable editor backend with draft change sets
```
