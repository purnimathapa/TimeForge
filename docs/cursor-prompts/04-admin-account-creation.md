# PROMPT 04 — In-App Admin Account Creation

Paste this entire file into Cursor Agent mode.

---

## Goal

Admins can create other **Admin** accounts from the UI (not only via `createsuperuser` or Django admin).

## Prerequisites

Prompt 03 complete.

## Pattern to follow

Mirror existing teacher creation:
- `academics/forms.py` — `TeacherCreationForm`
- `academics/views.py` — `TeacherCreateView` (creates User + TeacherProfile)

For Admin accounts, **only User is needed** (no profile model).

## Tasks

### 1. Form — `accounts/forms.py`

Add `AdminCreationForm(UserCreationForm)`:
- Fields: username, email, first_name, last_name, password1, password2
- `save()` sets `user.role = User.RoleChoices.ADMIN`

### 2. View — `accounts/views.py`

Add `AdminCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView)`:
- `allowed_roles = ['ADMIN']`
- `form_class = AdminCreationForm`
- `template_name = 'accounts/admin_form.html'` (new — copy structure from `accounts/teacher_form.html` or use `partials/base_form.html` with crispy)
- `success_url` → home or accounts profile list

### 3. URL — `accounts/urls.py`

```python
path('admin/create/', views.AdminCreateView.as_view(), name='admin_create'),
```

(Do not conflict with Django's `/admin/` — this is under `/accounts/admin/create/`)

### 4. Navigation

`templates/partials/sidebar.html` — inside admin block, add links:
- Create Teacher → `academics:teacher_create` (existing)
- Create Admin → `accounts:admin_create`

### 5. Optional (only if quick)

"Generate password" button using `secrets` module; show once in success message. Skip if it expands scope.

## Out of scope

- Class Representative (Prompt 05)
- Changing Teacher creation flow

## Tests — `accounts/tests.py`

- Admin can GET/POST create admin → success, new user has role ADMIN
- Teacher GET/POST → 403

## Acceptance criteria

- [ ] UI creates Admin without CLI
- [ ] Tests pass

## Git commit message

```
feat: admin UI to create admin accounts
```
