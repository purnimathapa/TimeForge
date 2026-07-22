# PROMPT 09A — Multi-Tenancy: School Model & Migrations

Paste this entire file into Cursor Agent mode.

**This is part 1 of 3. Do not scope views yet — models and migrations only.**

---

## Goal

Introduce the `School` tenant model and add nullable-then-required FKs with a safe data migration for existing rows.

## Prerequisites

Prompt 08 complete. Full test suite green.

## Design doc (required output)

Create `docs/MULTI_TENANCY.md` documenting:

1. **Direct `school` FK on:** `User`, `Department`, `Room`, `Semester`
2. **Transitive only (no redundant FK):** e.g. `Subject` via `department`, `Section` via `department`+`semester`, `Timetable` via `semester`, etc. — list each model explicitly
3. **Room modeling fix (v2 Gap 4.5):** `Room.school` direct FK required; `Room.department` stays optional/informational
4. **User.school:** required for non-superuser staff accounts; superuser may be null (document `createsuperuser` flow)

## Tasks

### 1. School model — `core/models.py`

```python
class School(models.Model):
    name = models.CharField(max_length=200, unique=True)
    code = models.SlugField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### 2. Add nullable FKs (migration 1)

- `accounts.User.school` → School, null=True, blank=True, on_delete=PROTECT
- `core.Department.school` → null=True
- `core.Room.school` → null=True (new field)
- `core.Semester.school` → null=True

### 3. Data migration (migration 2)

- Create `School` row: name="Default School", code="default"
- Backfill all existing User (non-superuser), Department, Room, Semester rows to that school
- Document in migration comments

### 4. Alter to non-null (migration 3)

- Set `null=False` on Department, Room, Semester school FKs
- User.school: null=False for normal users — handle superusers (keep nullable for is_superuser OR set default school — document choice in MULTI_TENANCY.md)

Run migrations against DB with existing seed data (`seed_db.py` or manual data), not only empty DB.

### 5. Admin registration

Register `School` in `core/admin.py` for bootstrap.

## Out of scope (Prompt 09B)

- Middleware
- View query scoping
- Isolation tests

## Tests (minimal for 09A)

- `core/tests.py`: School create, FK backfill smoke test if feasible

## Acceptance criteria

- [ ] `docs/MULTI_TENANCY.md` exists
- [ ] Migrations apply on populated DB
- [ ] Every Department/Room/Semester has school_id
- [ ] Room has direct school FK

## Git commit message

```
feat: add School model and tenant foreign keys with data migration
```
