# Multi-Tenancy Design (TimeForge)

TimeForge uses a **single-database, shared-schema** multi-tenant model. Each institution is a `School` row; tenant isolation is enforced by foreign keys and (in Prompt 09B+) query scoping on views.

## Tenant root: `core.School`

| Field       | Purpose                          |
|------------|-----------------------------------|
| `name`     | Display name (globally unique)    |
| `code`     | Slug identifier (globally unique) |
| `is_active`| Whether the school accepts use    |

Bootstrap school created by data migration: **Default School** (`code=default`).

## Direct `school` foreign keys

These models carry an explicit `school_id` and are the primary scoping anchors:

| Model              | App        | Notes                                      |
|--------------------|------------|--------------------------------------------|
| `User`             | accounts   | See [User.school](#userschool) below       |
| `Department`       | core       | Required after migration 09A               |
| `Room`             | core       | Required; see [Room modeling](#room-modeling) |
| `Semester`         | core       | Required after migration 09A               |

## Transitive tenancy (no redundant `school` FK)

Tenant is derived through the chain listed below. Do **not** add duplicate `school` columns on these models unless a future performance audit requires denormalization.

| Model               | App        | Tenant path                                              |
|---------------------|------------|----------------------------------------------------------|
| `Subject`           | academics  | `department → school`                                    |
| `Section`           | academics  | `department → school` and `semester → school` (same school) |
| `TeacherProfile`    | academics  | `user → school` (primary); optional `department → school` for affiliation |
| `ClassRepProfile`   | academics  | `section → department/semester → school`                 |
| `ClassSession`      | academics  | `section → … → school`                                   |
| `TeacherAvailability` | scheduling | `teacher → user → school`                              |
| `Constraint`        | scheduling | `semester → school` (plus target FKs scoped in 09B)      |
| `Timetable`         | timetable  | `semester → school`                                      |
| `TimetableSlot`     | timetable  | `timetable → semester → school`; `room → school`         |
| `DraftChangeSet`    | timetable  | `timetable → semester → school`                          |
| `DraftMove`         | timetable  | `change_set → timetable → … → school`                    |

### Global / undecided in 09A

| Model      | App        | Status in 09A                                            |
|------------|------------|----------------------------------------------------------|
| `TimeSlot` | scheduling | **Institution-wide calendar grid** — no `school` FK yet. Prompt 09B will document whether timeslots are global or per-school. Engine loads all active slots today. |

## Room modeling (v2 Gap 4.5)

- **`Room.school`** — **required** direct FK. Defines which tenant owns the room for scheduling and exports.
- **`Room.department`** — **optional, informational**. Indicates a home department (signage, maintenance) but does not determine tenancy. A room belongs to the school even when `department` is null.

## User.school

| Account type                         | `school` requirement                                      |
|--------------------------------------|-----------------------------------------------------------|
| Admin, Teacher, Class Rep (staff)    | **Required** at application layer (enforced in 09B forms)   |
| Django superuser (`is_superuser=True`) | **May be null** — platform operator across all schools   |

### `createsuperuser` flow

1. Run `python manage.py createsuperuser` as usual.
2. Leave `school` unset (null) for a cross-tenant operator account.
3. Optionally assign a school later in Django admin if the superuser should default to one tenant when using the app UI.
4. Non-superuser accounts created via admin or in-app forms must have `school` set before they can use tenant-scoped features (09B).

**Migration choice (09A):** `User.school` remains **nullable at the database level** so superusers are not forced into Default School. Department, Room, and Semester `school` columns are **non-null** after the backfill migration.

## Migration strategy (Prompt 09A)

1. **Nullable FKs** — Add `School` and nullable `school` on `User`, `Department`, `Room`, `Semester`.
2. **Data migration** — Create Default School; backfill all existing departments, rooms, semesters, and non-superuser users.
3. **Non-null core FKs** — Alter `Department`, `Room`, `Semester` to `null=False`. `User.school` stays nullable for superusers.

## Query scoping (Prompt 09B — not yet implemented)

Views will filter via `request.user.school` and middleware-attached `request.school`. See `docs/cursor-prompts/09b-multitenancy-scoping.md`.

Superuser behavior when `request.school is None`: documented in 09B (see all tenants vs require school selection).

## Out of scope (09A)

- Middleware and view queryset filtering
- Cross-tenant isolation tests
- Per-school unique constraints on `Department.code` / `Room.name` (future hardening)
- Subscription / billing (FR14)
