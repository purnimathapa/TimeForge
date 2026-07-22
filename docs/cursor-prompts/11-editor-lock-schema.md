# PROMPT 11 — Editor Lock & TimetableSlot Schema Honesty

Paste this entire file into Cursor Agent mode.

**Prerequisites:** Prompt 06B complete. Can run after 07.

---

## Goal

1. Prevent two admins editing the same timetable concurrently (v2 concurrency control).  
2. Fix mismatch between `TimetableSlot` docstring and actual DB constraints.

## Tasks

### 1. Edit lock model — `timetable/models.py`

```python
class TimetableEditLock(models.Model):
    timetable = models.OneToOneField(Timetable, on_delete=models.CASCADE, related_name='edit_lock')
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    locked_at = models.DateTimeField(auto_now=True)

    LOCK_TIMEOUT_MINUTES = 10  # document in docstring
```

Helper function `acquire_lock(timetable, user)` / `is_locked_by_other(timetable, user)` — timeout based on `locked_at`.

Migrate.

### 2. Enforce lock

In these admin-only views, before mutating:
- `ValidateBatchView`, `PublishChangeSetView`, `DiscardChangeSetView`
- Optionally grid view context: show banner "Being edited by X" if locked by other

On successful publish or discard of change set → release lock.

On acquire by new user after timeout → steal lock (document behavior).

Return 409 JSON if locked: `{ok: false, error: "...", locked_by: "..."}`

### 3. TimetableSlot unique_together fix

Read `timetable/models.py` class docstring — claims `(timetable, timeslot, teacher)` unique_together.

**Choose one:**
- **A)** Add the missing constraint to `Meta.unique_together` (research PostgreSQL nullable unique behavior for nullable teacher FK — docstring already mentions NULL semantics)
- **B)** Remove the claim from docstring if DB constraint is intentionally omitted

Implement A unless migration risk is high — engine already prevents teacher double-booking; DB constraint is defense-in-depth.

### 4. UI

On `grid.html` admin editor: show lock warning banner when another user holds lock.

## Out of scope

- WebSocket presence detection
- Tab-close unlock (timeout is sufficient)

## Tests — `timetable/tests.py`

1. User A acquires lock; User B validate-batch → 409
2. After timeout, User B can acquire
3. Publish releases lock
4. If added unique_together: attempt double teacher slot insert fails at DB level

## Acceptance criteria

- [ ] Concurrent edit blocked with clear message
- [ ] Docstring and Meta agree on constraints
- [ ] Tests pass

## Git commit message

```
feat: timetable edit lock and align slot uniqueness with docs
```
