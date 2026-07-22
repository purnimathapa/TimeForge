# PROMPT 01 — Security & Repository Hygiene

Paste this entire file into Cursor Agent mode with the TimeForge repo open.

---

## Goal

Fix committed security/repo hygiene issues before any feature work.

## Prerequisites

None.

## Ground rules

- Read `.cursorrules` — no stack changes.
- **Do not** modify application logic in this prompt.

## Tasks

### 1. Remove credentials from README

Find any real-looking database username/password in `README.md` (e.g. literal `Purnim@123`). Replace with placeholders (`your_username`, `your_password`). Add one line pointing to `.env.example` — settings already use `python-decouple`.

### 2. Untrack `venv/`

```bash
git rm -r --cached venv/
```

Verify: `git ls-files | grep '^venv/'` returns nothing. **Do not** delete the local `venv/` folder.

### 3. Verify `.env` was never committed

Run `git log --all -- .env`. If any history exists, flag for the human to rotate secrets — you cannot rotate DB passwords yourself.

## Out of scope

- Feature code, migrations, views.

## Acceptance criteria

- [ ] README has no real credentials
- [ ] `venv/` not tracked
- [ ] `.env` never in git history (or human notified to rotate)
- [ ] Your summary **explicitly tells the human to rotate** the README password on any DB where it was used

## Git commit message

```
chore: remove leaked credentials from README and untrack venv
```
