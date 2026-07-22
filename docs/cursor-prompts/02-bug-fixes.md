# PROMPT 02 — Known Bug Fixes (Pre–Viewer Access)

Paste this entire file into Cursor Agent mode.

---

## Goal

Fix small bugs that block correct viewer/timetable behavior in later prompts.

## Prerequisites

Prompt 01 complete.

## Tasks (only these files unless a import forces a touch)

### 1. Teacher portal related_name bug

`academics/views.py` — `TeacherPortalView` uses `getattr(user, 'teacherprofile')` but the model uses `related_name='teacher_profile'`. Fix to `teacher_profile`.

### 2. Admin dashboard timetable state

`dashboard/views.py` + `templates/dashboard/admin_dashboard.html` — the admin dashboard always shows "No Timetable Generated Yet". Pass context indicating whether a timetable exists for the active semester (and optionally latest version/status). Show the empty card only when none exists.

### 3. Published vs draft for non-admins (foundation)

In `dashboard/views.py` teacher branch: `has_timetable` should mean a **PUBLISHED** timetable exists for the active semester, not any DRAFT.

In `timetable/views.py` helper `_get_timetable()`: when `request.user` is not admin, **only** return PUBLISHED timetables (no DRAFT fallback). Admins keep current behavior (PUBLISHED then DRAFT).

### 4. CLI generate_timetable error field

`scheduling/management/commands/generate_timetable.py` — use `result.failure_reason` not `result.message` (field does not exist on `ScheduleResult`).

### 5. Room capacity in engine I/O

`scheduling/engine/models_io.py` — include `student_count` in `SectionData` when loading sections. Update `scheduling/engine/data_types.py` if needed. Ensure `room_has_capacity` in `constraints.py` can actually fail when section exceeds room capacity.

## Out of scope

- Role changes, new models, editor rewrite, multi-tenancy.

## Tests

Add or extend tests for:
- Teacher portal resolves profile when user has `teacher_profile`
- `_get_timetable` non-admin does not return DRAFT
- Optional: capacity constraint test in `scheduling/tests/test_engine.py` if quick

Run: `python manage.py test`

## Acceptance criteria

- [ ] All tests pass
- [ ] Teacher portal works for linked teacher users
- [ ] Admin dashboard reflects real timetable state
- [ ] Non-admin timetable resolution prefers published-only

## Git commit message

```
fix: portal profile, dashboard state, published-only viewers, engine capacity I/O
```
