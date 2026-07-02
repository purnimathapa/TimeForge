# TimeForge — Django App Boundaries

This document lists every Django app to be created for TimeForge and defines a single, non-overlapping responsibility for each. App names are stable contracts—rename only before models exist.

## App Registry

| App           | Package path   | One-sentence responsibility |
|---------------|----------------|-----------------------------|
| `accounts`    | `accounts/`    | Manages user registration, login, logout, and the custom User model with a role field for authorization across the system. |
| `core`        | `core/`        | Owns shared organizational entities—departments, rooms, and semesters—that other apps reference but do not duplicate. |
| `academics`   | `academics/`   | Models the teaching domain: subjects, student sections, teacher profiles, and which subjects each section must take in a given semester. |
| `scheduling`  | `scheduling/`  | Defines time slots, scheduling constraints, class sessions to be placed, and the standalone Python scheduling engine callable from views and management commands. |
| `timetable`   | `timetable/`   | Stores generated timetables and their slot assignments, provides the manual editor, read-only views, and export endpoints. |
| `dashboard`   | `dashboard/`   | Serves role-aware home pages and summary widgets that aggregate data from the other apps without owning domain models. |

## Model Ownership

| Entity / concern              | Owner app     |
|-------------------------------|---------------|
| User, role, auth views        | `accounts`    |
| Department, Room, Semester    | `core`        |
| Subject, Section, Teacher, TeacherSubject, SectionOffering | `academics` |
| TimeSlot, Constraint, ClassSession, ScheduleRun | `scheduling` |
| Timetable, TimetableSlot      | `timetable`   |
| Dashboard metrics (queries only) | `dashboard` |

## Dependency Direction

Dependencies should flow in one direction to avoid circular imports:

```
accounts  ──►  (referenced by all apps via AUTH_USER_MODEL)

core  ──►  academics  ──►  scheduling  ──►  timetable
                              ▲
                              │
                         dashboard (read-only queries across apps)
```

- `core` does not import from `academics`, `scheduling`, or `timetable`.
- `scheduling` may import models from `core` and `academics` when building engine inputs.
- `timetable` may import from `scheduling`, `academics`, and `core`.
- `dashboard` may import models for read queries only; it defines no foreign keys to other apps’ tables.

## URL Namespace Plan

Each app exposes its URLs under a prefix in the root URLconf:

| App           | URL prefix (planned)   |
|---------------|------------------------|
| `accounts`    | `/accounts/`           |
| `core`        | `/core/`               |
| `academics`   | `/academics/`          |
| `scheduling`  | `/scheduling/`         |
| `timetable`   | `/timetable/`          |
| `dashboard`   | `/` (home)             |

## What Does Not Get Its Own App

| Concern                         | Where it lives                          |
|---------------------------------|-----------------------------------------|
| Scheduling engine algorithm     | `scheduling/services/` (not a Django app) |
| Project settings & root URLs    | `config/`                               |
| Shared base templates           | `templates/` at project root            |
| Site-wide static CSS            | `static/` at project root               |

## Registration Checklist (later prompts)

When apps are created, add them to `INSTALLED_APPS` in this order (dependencies first):

1. `accounts`
2. `core`
3. `academics`
4. `scheduling`
5. `timetable`
6. `dashboard`

Set `AUTH_USER_MODEL = "accounts.User"` before the first migration that creates the User table.
