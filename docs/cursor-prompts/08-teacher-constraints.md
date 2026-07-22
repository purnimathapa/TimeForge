# PROMPT 08 — Teacher-Centred Constraints (Partial Catalogue)

Paste this entire file into Cursor Agent mode.

---

## Goal

Extend the constraint system with **two teacher-centred soft constraints** and wire `TeacherProfile.max_hours_per_day` into the engine. Do **not** implement the full 34-constraint catalogue.

## Prerequisites

Prompt 07 complete.

## Current state

- `Constraint.ConstraintType`: 4 choices; `CUSTOM` never evaluated
- Engine soft penalties: `MAX_DAILY_HOURS`, `NO_ADJACENT_GAPS` only
- `TeacherProfile.max_hours_per_day/week` stored but not used by engine

## Tasks

### 1. New constraint types — `scheduling/models.py`

Add:
```python
MAX_CONSECUTIVE_PERIODS = 'MAX_CONSECUTIVE_PERIODS', 'Max Consecutive Periods'
PREFERRED_TEACHING_TIME = 'PREFERRED_TEACHING_TIME', 'Preferred Teaching Time'
```

Add field:
```python
max_consecutive_periods = models.PositiveIntegerField(null=True, blank=True)
```

For `PREFERRED_TEACHING_TIME`, use `custom_parameters` JSON (e.g. `{preferred_days: [1,2], period_start: 1, period_end: 4}`) — document shape in model help_text.

Update `Constraint.clean()` to validate required fields per type (mirror existing pattern).

Update `templates/scheduling/constraint_form.html` if needed to show new fields.

Migrate.

### 2. Engine datatypes — `scheduling/engine/data_types.py`

Extend `ConstraintData` with:
- `max_consecutive_periods: Optional[int] = None`
- Preferred-time fields (e.g. `preferred_days: frozenset`, `preferred_period_start/end`) — pick concrete shape, document in docstring

### 3. models_io — `scheduling/engine/models_io.py`

Map new ORM fields → `ConstraintData`.

**Synthesize soft daily limit:** For each teacher, if no explicit soft/hard `MAX_DAILY_HOURS` constraint row targets them, inject a synthetic soft constraint from `TeacherProfile.max_hours_per_day` (document in comment). Do **not** synthesize weekly — add comment on `max_hours_per_week` that enforcement is future work.

### 4. Penalty handlers — `scheduling/engine/constraints.py`

In `compute_penalty()`:

**MAX_CONSECUTIVE_PERIODS (soft):** Reuse per-teacher per-day sorted period lists (same structure as gap detection). Find longest consecutive run; penalize `(run_length - max) * weight` when over limit.

**PREFERRED_TEACHING_TIME (soft only):** If placement day/period outside preferred range, add `weight`. Never hard-reject in `is_hard_feasible`.

Leave `CUSTOM` unchanged — still unevaluated.

### 5. Tests — `scheduling/tests/test_engine.py`

Add tests matching existing style:
1. 4 consecutive periods with max_consecutive=3 → penalty > 0
2. Placement outside preferred window → penalty > 0
3. Synthesized daily limit from teacher profile when no explicit constraint row
4. Existing tests still pass

## Out of scope

- Remaining 28 constraints from v2 catalogue
- `CUSTOM` JSON interpreter
- `max_hours_per_week` enforcement
- UI for bulk constraint templates

## Acceptance criteria

- [ ] 6 constraint types in DB
- [ ] Admin can create new types via existing CRUD
- [ ] Engine tests pass including new cases
- [ ] Full test suite green

## Git commit message

```
feat: teacher-centred soft constraints and profile daily limit wiring
```
