# PROMPT 05 — Class Representative Role

Paste this entire file into Cursor Agent mode.

---

## Goal

Add the **Class Representative (CR)** role end-to-end: model, creation UI, dashboard, nav, read access — same institution-wide read as Teachers (Prompt 03), defaulting to their section.

## Prerequisites

Prompts 03 and 04 complete.

## Tasks

### 1. User role — `accounts/models.py`

Add to `RoleChoices`:
```python
CLASS_REP = 'CLASS_REP', 'Class Representative'
```
Add `is_class_rep()` helper matching `is_admin()` / `is_teacher()`.

Generate and run migration for `accounts`.

### 2. Profile model — `academics/models.py`

```python
class ClassRepProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='class_rep_profile')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='class_reps')
    is_active = models.BooleanField(default=True)
```

Migrate `academics`.

### 3. Creation form & view — `accounts/forms.py`, `accounts/views.py`

`ClassRepCreationForm(UserCreationForm)`:
- User fields + `section = ModelChoiceField(Section.objects.filter(is_active=True))`
- `save()` in `transaction.atomic()`: create User with role CLASS_REP, then ClassRepProfile

`ClassRepCreateView` — same pattern as AdminCreateView, `allowed_roles = ['ADMIN']`, template `accounts/class_rep_form.html`.

URL: `path('class-rep/create/', ..., name='class_rep_create')`

### 4. Timetable read access — `timetable/views.py`

Add `'CLASS_REP'` everywhere Prompt 03 added `'TEACHER'` for read-only grids and room/section exports.

`SectionTimetableView._get_selected_section()`: if user is CLASS_REP, default to `request.user.class_rep_profile.section`.

### 5. Dashboard — `dashboard/views.py`

Add branch:
```python
elif self.request.user.role == 'CLASS_REP':
    return ['dashboard/class_rep_dashboard.html']
```

Context: `has_timetable` = published timetable exists for active semester (same as teacher). Include section name from profile.

Create `templates/dashboard/class_rep_dashboard.html` — match `teacher_dashboard.html` structure (extend `base.html`).

### 6. Navigation

`templates/partials/sidebar.html` — new `{% elif user.role == 'CLASS_REP' %}` block:
- My section timetable (section grid)
- Room timetable (for finding free rooms)
- Profile

Admin sidebar: add "Create Class Rep" link.

Navbar: CR must not see Generate Timetable or admin-only items.

### 7. Register in admin (optional)

`academics/admin.py` — register ClassRepProfile for debugging.

## Out of scope

- Batch editor, timetable publish, multi-tenancy

## Tests

- `accounts/tests.py`: CR creation, role set, profile linked
- `timetable/tests.py`: CLASS_REP GET grids 200; POST move 403; section default
- `academics/tests.py`: ClassRepProfile basic

## Acceptance criteria

- [ ] Admin creates CR tied to section via UI
- [ ] CR logs in, lands on dashboard, browses section/room/teacher grids
- [ ] CR cannot mutate timetable or access admin CRUD
- [ ] All tests pass

## Git commit message

```
feat: class representative role, profile, and read-only access
```
