# PROMPT 03 — Teacher Institution-Wide Read Access

Paste this entire file into Cursor Agent mode.

---

## Goal

Teachers get **read-only** institution-wide timetable browsing (room, section, any teacher grid) matching the v2 Viewer intent — without write access.

## Prerequisites

Prompt 02 complete.

## Current state

- `RoomTimetableView`, `SectionTimetableView`: `allowed_roles = ['ADMIN']`
- `TeacherTimetableView`: Teachers locked to own profile unless admin uses `?teacher_id=`
- `ExportTimetableView`: blocks room/section/full export for non-admins

## Tasks

### 1. Grid view permissions

In `timetable/views.py`:
- `RoomTimetableView`, `SectionTimetableView`: `allowed_roles = ['ADMIN', 'TEACHER']`
- `TeacherTimetableView._get_selected_teacher()`: allow **any authenticated Teacher or Admin** to pass `?teacher_id=`. Defaults unchanged: Admin → first teacher alphabetically; Teacher → own profile.

### 2. Export permissions

In `ExportTimetableView.get()`:
- Block only `'full'` scope for non-admins
- Allow `'room'` and `'section'` export for Teachers (they can browse those grids)
- `'teacher'` scope already allowed for own export — keep working

Add `# TODO` if product should later restrict teacher-scope export to self only.

### 3. Templates

`templates/timetable/grid.html`:
- Teachers see **version selector** (published versions only per Prompt 02)
- Keep **Full PDF/Excel** buttons admin-only
- Keep drag-and-drop editor config admin-only (`{% if user.is_admin %}`)

### 4. Do NOT change

- `MoveSlotView`, `UnlockSlotView`, `GenerateTimetableView` — remain admin-only
- `ConflictReportView`, `ReportsView` — remain admin-only unless already admin-only (verify)

## Tests (`timetable/tests.py`)

Add cases:
- Teacher GET `/timetable/room/`, `/timetable/section/`, `/timetable/teacher/` → 200
- Teacher POST `/timetable/slots/move/` → 403
- Teacher GET room/section export → 200
- Teacher GET full export → 403

## Acceptance criteria

- [ ] Teachers browse institution grids via dropdowns
- [ ] No write/export-full access for teachers
- [ ] Tests pass

## Git commit message

```
feat: institution-wide read-only timetable access for teachers
```
