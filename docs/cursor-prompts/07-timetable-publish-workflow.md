# PROMPT 07 — Timetable Version Publish Workflow (DRAFT → PUBLISHED)

Paste this entire file into Cursor Agent mode.

**Note:** This is **official timetable publish** (FR10), not batch move publish from Prompt 06.

---

## Goal

Admins can publish a **DRAFT timetable version** as the institution's official schedule, archive the previous published version, and ensure Viewers (Teacher/CR) only ever see **PUBLISHED** timetables.

## Prerequisites

Prompts 02 (published-only foundation) and 06B complete.

## Tasks

### 1. Model fields — `timetable/models.py`

Add to `Timetable`:
- `published_at = models.DateTimeField(null=True, blank=True)`
- `published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='published_timetables')`

Migrate.

### 2. Views — `timetable/views.py`

**`PublishTimetableView`** (POST, admin-only):
- Input: `timetable_id`
- Require status == DRAFT
- In `transaction.atomic()`:
  - Set any existing PUBLISHED timetable for same semester → ARCHIVED
  - Set this timetable → PUBLISHED, `published_at=now()`, `published_by=request.user`
- Redirect with success message

**`DiscardDraftTimetableView`** (POST, admin-only):
- Delete DRAFT timetable and its slots OR mark ARCHIVED — pick one, document in view docstring (prefer ARCHIVED if audit matters)

Wire URLs:
```python
path('<int:pk>/publish/', ..., name='publish_timetable'),
path('<int:pk>/discard/', ..., name='discard_timetable'),
```

### 3. UI

**`templates/timetable/detail.html`** — if DRAFT and admin: Publish + Discard buttons (POST forms with CSRF)

**`templates/dashboard/admin_dashboard.html`** — show latest timetable status (DRAFT/PUBLISHED) and link to detail

**After generation** (`GenerateTimetableView`): redirect to detail with message "Review draft, then publish when ready"

### 4. Enforce viewer access (verify Prompt 02)

Confirm `_get_timetable()` for non-admin returns **only** PUBLISHED.

Confirm teacher/CR dashboards use published-only `has_timetable`.

Admins may still preview DRAFT via `?timetable_id=` on grids.

### 5. Optional audit display

On detail template show `published_at` / publisher name when PUBLISHED.

## Out of scope

- Multi-tenancy scoping (Prompt 09)
- Email notifications on publish

## Tests — `timetable/tests.py`

1. Publish DRAFT → status PUBLISHED, previous PUBLISHED → ARCHIVED
2. Teacher cannot see DRAFT after publish (grid uses published)
3. Non-admin POST publish → 403
4. Discard draft removes/archives correctly

## Acceptance criteria

- [ ] Full lifecycle: generate → DRAFT → publish → viewers see it
- [ ] Atomic publish (one published per semester)
- [ ] Tests pass

## Git commit message

```
feat: publish and discard draft timetable versions
```
