# PROMPT 09C — Multi-Tenancy: Isolation Test Suite

Paste this entire file into Cursor Agent mode.

**Prerequisites:** Prompt 09B complete.

---

## Goal

Add the **release-blocker** cross-tenant isolation test suite specified in v2 NFR1.

## Tasks

### 1. New file — `core/tests/test_tenant_isolation.py`

Docstring: state these tests are release-blockers for any multi-school deployment.

### 2. Test fixture setup

Create two schools: `School A`, `School B`.

For **each** school, create minimal parallel dataset:
- Department, Room, Semester (active for A only or both — document)
- Admin User linked to school
- Teacher User + TeacherProfile
- Section, Subject, ClassSession
- TimeSlot(s), Timetable (PUBLISHED), TimetableSlot

Use factory helpers or setUp methods to avoid 500 lines of duplication.

### 3. Assertions — School A admin must NEVER see School B data

For each case, authenticate as School A admin and assert empty/wrong results do not leak:

| Area | Test |
|------|------|
| Lists | department_list, room_list, teacher_list, timetable list |
| Detail by PK | GET School B timetable PK → 404 |
| Grids | teacher_view, room_view, section_view with School B IDs in query params |
| Export | export with School B entity IDs → 404 or empty |
| JSON editor | validate-batch / publish with School B timetable_id → 403/404 |
| Generate | POST generate cannot target School B semester |

Also test **School A Teacher** cannot see School B published timetable via grid.

### 4. Positive control

School A admin **can** see School A timetable slots in grid (sanity check tests aren't broken).

### 5. CI note

Add comment that this module should run first in CI when configured.

## Out of scope

- New features
- Performance tests

## Acceptance criteria

- [ ] `python manage.py test core.tests.test_tenant_isolation` passes
- [ ] Full suite passes
- [ ] At least 10 distinct isolation scenarios covered

## Git commit message

```
test: cross-tenant isolation suite for school-scoped data
```
