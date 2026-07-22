# PROMPT 10 — My Routine (Mobile-First Viewer UX)

Paste this entire file into Cursor Agent mode.

**Prerequisites:** Prompt 07 (published timetables). Can run in parallel with Prompts 08–09 if 07 is done.

---

## Goal

Implement v2 **FR12 / NFR10**: Teachers and Class Reps land on a **My Routine** view with a prominent **next class** card and scrollable weekly grid below — mobile-first layout.

## Tasks

### 1. View — `timetable/views.py` or `dashboard/views.py`

Add `MyRoutineView(LoginRequiredMixin, TemplateView)`:
- Allowed: TEACHER, CLASS_REP (use role check in dispatch or mixin)
- Resolve **published** timetable for active semester (reuse `_get_timetable` / helpers from Prompt 02/07)
- **Teacher:** filter slots to `request.user.teacher_profile`
- **CR:** filter slots to `class_rep_profile.section` (via class_session__section)

Context:
- `next_slot` — upcoming TimetableSlot by current datetime vs timeslot start (use `Asia/Kathmandu` timezone from settings)
- `next_slot_countdown` — human-readable "in 25 minutes" / "Now"
- `today_slots`, `week_grid` — same grid structure as `grid.html` or simplified

### 2. Template — `templates/timetable/my_routine.html`

Mobile-first CSS (Bootstrap utilities only — no Tailwind):
- Large card at top: subject, room, time, teacher (for CR show section context)
- Full week grid below (compact on mobile)
- Link: "Browse institution timetable" → room grid or a small hub page

Extend `base.html`. Test at 375px width.

### 3. Dashboard integration

**Teacher dashboard** (`templates/dashboard/teacher_dashboard.html`):
- Primary CTA → `timetable:my_routine` (new URL name)
- De-emphasize generic "View My Timetable" if redundant

**CR dashboard** — same primary CTA

### 4. URL — `timetable/urls.py`

```python
path('my-routine/', views.MyRoutineView.as_view(), name='my_routine'),
```

### 5. Sidebar

Teacher/CR sidebar: put **My Routine** first item.

### 6. Institution directory hub (lightweight)

Optional single template `templates/timetable/directory.html` with links to teacher/room/section grids — or link directly from My Routine footer. Keep minimal.

## Out of scope

- Push notifications
- Native app
- Building filter

## Tests

- Teacher with published slots → 200, context has `next_slot` when applicable
- CR sees section-scoped slots
- No published timetable → friendly empty state

## Acceptance criteria

- [ ] Phone-width layout usable without horizontal scroll on routine page
- [ ] Next class visible above fold on mobile
- [ ] Only PUBLISHED timetables used
- [ ] Tests pass

## Git commit message

```
feat: mobile-first My Routine view for teachers and class reps
```
