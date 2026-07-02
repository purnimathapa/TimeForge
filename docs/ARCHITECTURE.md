# TimeForge — Architecture & Technical Design

TimeForge is a university timetable scheduling system. This document describes the Django + PostgreSQL architecture adapted from the original MERN + FastAPI proposal. All later implementation prompts should treat this file as the source of truth for system shape and boundaries.

## Technology Stack

| Layer        | Choice                                      |
|--------------|---------------------------------------------|
| Backend      | Django 6.x (Python)                         |
| Database     | PostgreSQL                                  |
| Frontend     | Django templates + server-rendered HTML     |
| Auth         | Django built-in auth + custom User model  |
| Scheduling   | Pure-Python engine module in `scheduling`   |

**Out of scope for this project:** React, Vue, Angular, Node.js, Express, MongoDB, FastAPI, Tailwind CSS, and any separate frontend SPA framework.

## Django Application Boundaries

TimeForge is split into six Django apps. Each app owns its models, views, URLs, and templates for its domain. Cross-app imports should go through well-defined model relationships and service functions—not circular view imports.

| App           | Responsibility (summary)                                      |
|---------------|---------------------------------------------------------------|
| `accounts`    | Authentication, custom User model, role-based access        |
| `core`        | Organizational structure: departments, rooms, semesters       |
| `academics`   | Teaching domain: subjects, sections, teachers, offerings      |
| `scheduling`  | Time slots, constraints, class sessions, scheduling engine    |
| `timetable`   | Generated timetables, manual editor, views, exports           |
| `dashboard`   | Role-aware landing pages and summary widgets                  |

See `docs/DJANGO_APPS.md` for the one-sentence charter of each app and `docs/DATA_MODEL.md` for the entity list.

## Request / Response Flow

Every browser interaction follows the same server-rendered path. There is no separate API tier and no client-side router.

```
Browser
  │
  │  HTTP GET/POST (HTML form or link)
  ▼
Django URLconf  (config/urls.py → app urls.py)
  │
  ▼
Middleware stack
  │  SecurityMiddleware → SessionMiddleware → CommonMiddleware
  │  → CsrfViewMiddleware → AuthenticationMiddleware → MessageMiddleware
  ▼
View  (function-based or class-based, per app)
  │
  ├─► @login_required / role decorator (accounts)
  │
  ├─► ORM queries via models in accounts, core, academics,
  │       scheduling, or timetable
  │       │
  │       ▼
  │   PostgreSQL  (timeforge database)
  │       │
  │       ◄── query results / writes
  │
  ├─► scheduling.services.engine  (when generating or validating)
  │       │
  │       ▼
  │   In-memory constraint solver (no HTTP, no subprocess)
  │
  ▼
Template render  (app templates + shared base)
  │
  ▼
HTTP response  (HTML + messages + CSRF token for next form)
  │
  ▼
Browser
```

### Typical flows by operation

**Read (e.g., view published timetable)**  
URL → view loads `Timetable` and related `TimetableSlot` rows via ORM → template renders grid → HTML response.

**Write (e.g., admin creates a room)**  
POST with CSRF token → view validates form → `Room.objects.create(...)` → redirect with success message.

**Generate timetable**  
POST from scheduler UI → view gathers `ClassSession`, `TimeSlot`, `Constraint`, and availability data → calls `scheduling.services.engine.generate_timetable(...)` → engine returns slot assignments and conflict report → view persists `Timetable` + `TimetableSlot` rows in a transaction → redirect to editor or conflict summary.

**Background / CLI generation**  
Management command `python manage.py generate_timetable` calls the same `generate_timetable(...)` entry point as the web view, ensuring one implementation for interactive and batch use.

## Scheduling Engine Location

The scheduling engine is **not** a separate microservice or Celery worker in v1. It lives as a standalone Python module inside the `scheduling` app:

```
scheduling/
  services/
    engine.py          # public API: generate_timetable, validate_timetable
    constraints.py     # constraint evaluation helpers
    solver.py          # placement / backtracking logic
  management/
    commands/
      generate_timetable.py   # CLI wrapper around engine.generate_timetable
```

### Design rules

1. **Single entry point** — Views and management commands import only from `scheduling.services.engine`, never from `solver.py` directly.
2. **Framework-agnostic core** — The solver receives plain Python dataclasses or dicts built from ORM instances; it does not import Django models internally (easier to unit test).
3. **Idempotent persistence** — Callers (view or command) own database transactions: the engine returns a result object; the caller writes `Timetable` / `TimetableSlot` rows.
4. **Same inputs, same outputs** — Web UI and CLI pass identical parameters (semester, department scope, constraint set) so behavior is consistent.

## Authentication & Authorization

### Custom User model

- App: `accounts`
- Model: `User` extends `AbstractUser` (or `AbstractBaseUser` + `PermissionsMixin` if email-login is preferred later).
- Required custom field: `role` with choices such as `admin`, `scheduler`, `teacher`, `viewer`.
- Setting: `AUTH_USER_MODEL = "accounts.User"` in project settings.

### Session-based login

Use Django’s stock session authentication:

- `django.contrib.auth.views.LoginView` / `LogoutView` (or thin wrappers in `accounts`).
- Password hashing via Django’s default PBKDF2 validators.
- `@login_required` on all views except login and public timetable views (if any).

### Role checks

Implement a small decorator or mixin in `accounts` (e.g., `role_required("scheduler", "admin")`) applied to views that mutate scheduling data or run generation. Teachers see only their own assignments; viewers see read-only published timetables.

### Teacher linkage

`academics.Teacher` holds a `OneToOneField` to `accounts.User`. Scheduling and timetable views resolve the current teacher through `request.user.teacher_profile` when `role == "teacher"`.

## Data Layer

- **Database:** PostgreSQL (`django.db.backends.postgresql`).
- **Migrations:** Per-app under each app’s `migrations/` package.
- **Entity definitions:** See `docs/DATA_MODEL.md` (plain-text ERD mirror; no ORM code in that doc).

Foreign keys generally flow:

```
accounts.User
core.Department, Room, Semester
academics.Subject, Section, Teacher, TeacherSubject, SectionOffering
scheduling.TimeSlot, ClassSession, Constraint, ScheduleRun
timetable.Timetable, TimetableSlot
```

## System Diagram (Text)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              BROWSER                                    │
│         HTML forms · Django templates · static CSS (no SPA)             │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ HTTP
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         DJANGO PROJECT (config)                         │
│  urls · middleware · settings · WSGI/ASGI                               │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
┌───────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   accounts    │       │      core       │       │   academics     │
│ User · roles  │       │ Dept · Room ·   │       │ Subject ·       │
│ login/logout  │       │ Semester        │       │ Section ·       │
└───────┬───────┘       └────────┬────────┘       │ Teacher ·       │
        │                        │                │ offerings       │
        │                        │                └────────┬────────┘
        │                        │                         │
        └────────────────────────┼─────────────────────────┘
                                 ▼
                    ┌────────────────────────┐
                    │      scheduling        │
                    │ TimeSlot · Constraint  │
                    │ ClassSession · Engine  │
                    │  (services/engine.py)  │
                    └───────────┬────────────┘
                                │ generates / validates
                                ▼
                    ┌────────────────────────┐
                    │      timetable         │
                    │ Timetable ·            │
                    │ TimetableSlot · editor │
                    │ exports · public views │
                    └───────────┬────────────┘
                                │
        ┌───────────────────────┘
        ▼
┌───────────────┐       ┌─────────────────────────────────────────────┐
│   dashboard   │       │              PostgreSQL                     │
│ role landing  │◄─────►│  persistent storage for all app models      │
│ summary stats │       └─────────────────────────────────────────────┘
└───────────────┘

Management command:  manage.py generate_timetable  ──►  scheduling.services.engine
```

## Cross-Cutting Concerns

- **Templates:** Shared base in `templates/base.html` at project level; app-specific templates under each app’s `templates/<app>/`.
- **Static files:** Project-level `static/` for site-wide CSS; avoid Tailwind build pipelines—plain CSS or minimal hand-written styles.
- **Messages:** Django messages framework for flash feedback after POST/redirect.
- **Admin:** Register core reference models in Django admin for bootstrap; primary UX remains custom views.
- **Exports:** PDF/CSV generation lives in `timetable` views, reading `TimetableSlot` querysets.

## Deployment Shape (Future)

Single Django process behind a reverse proxy (e.g., gunicorn + nginx). PostgreSQL on the same host or managed service. No Node build step. Static files collected via `collectstatic`.

## Document Map

| Document              | Purpose                                      |
|-----------------------|----------------------------------------------|
| `docs/ARCHITECTURE.md`| This file — system flow and design decisions |
| `docs/DJANGO_APPS.md` | App list and one-line responsibilities       |
| `docs/DATA_MODEL.md`  | Entity list mirroring proposal ERD Figure 3.2|
