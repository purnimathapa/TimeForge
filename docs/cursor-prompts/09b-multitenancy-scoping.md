# PROMPT 09B — Multi-Tenancy: Middleware & Query Scoping

Paste this entire file into Cursor Agent mode.

**Prerequisites:** Prompt 09A merged and migrated.

**This is the largest prompt — focus only on scoping. Do not write isolation tests yet (09C).**

---

## Goal

Every school-scoped query filters by `request.user.school`. Attach school to the request via middleware.

## Tasks

### 1. Middleware — `accounts/middleware.py` (new)

```python
class TenantMiddleware:
    def __init__(self, get_response): ...
    def __call__(self, request):
        request.school = None
        if request.user.is_authenticated and hasattr(request.user, 'school_id'):
            request.school = request.user.school
        return self.get_response(request)
```

Register in `timeforge/settings/base.py` **after** `AuthenticationMiddleware`.

### 2. Helper — `core/tenant.py` or `accounts/tenant.py` (new, small)

```python
def school_filter(qs, request):
    if request.user.is_superuser and request.school is None:
        return qs  # document: superuser sees all, or require school — pick one in MULTI_TENANCY.md
    return qs.filter(school=request.school)
```

Use consistent pattern across apps.

### 3. Audit and update views — grep-driven

Search `.objects.` in views for school-scoped models:

**core:** Department, Room, Semester  
**accounts:** User (admin user lists if any)  
**academics:** Subject, Section, TeacherProfile, ClassSession, ClassRepProfile  
**scheduling:** TimeSlot (global or per-school? — **decide in MULTI_TENANCY.md**; if global institution calendar, document why; if per-school, add FK in follow-up or scope via semester), Constraint, TeacherAvailability  
**timetable:** Timetable, TimetableSlot, DraftChangeSet  
**dashboard:** all aggregate counts filter by school  

For each view/list/create:
- Filter querysets by `request.school` (direct or via semester/department chain)
- On create forms, set school from request or infer from parent FK
- Object detail by PK: return 404 if object not in user's school (prevent ID guessing)

**Priority endpoints:**
- All CRUD list/create in core, academics, scheduling
- Timetable grids, exports, batch editor JSON endpoints from Prompt 06
- Generate timetable, publish timetable

### 4. Forms

Ensure ModelChoiceField querysets are school-scoped (teachers, sections, rooms, semesters).

### 5. Engine I/O

`load_schedule_input(semester_id)` — caller must pass semester already verified for school; add optional `school_id` assert inside models_io if cheap.

### 6. Login / superuser

Document behavior when `request.school` is None. Do not break login.

## Out of scope

- Subscription/billing (FR14)
- Full isolation test suite (09C)
- Building entity

## Manual smoke test checklist

After changes, as School A admin:
- Lists show only School A data
- Guessing School B PK in URL → 404/403

## Acceptance criteria

- [ ] Middleware registered
- [ ] Grep audit documented in PR summary (list files changed)
- [ ] No unscoped list views remain for school-owned models
- [ ] `python manage.py test` passes (existing tests may need school fixtures updated)

## Git commit message

```
feat: tenant middleware and school-scoped view querysets
```

## Note for Cursor

If existing tests fail due to missing School FK on fixtures, **fix tests in this prompt** by creating Default School in test setUp — do not defer.
