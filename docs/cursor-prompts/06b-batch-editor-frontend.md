# PROMPT 06B — Batch Editor Frontend + SortableJS

Paste this entire file into Cursor Agent mode.

**Prerequisites:** Prompt 06A merged and tested.

---

## Goal

Update the admin timetable grid so drags **stage** moves locally, then **Check Changes → Publish** or **Discard**. Add SortableJS for touch support.

## Ground rules

- **Vanilla JS only** — no Alpine, htmx, React, npm build step
- Match existing `static/js/timetable_editor.js` style (IIFE, `getCookie`, `showToast`)
- Keep `UnlockSlotView` flow unchanged (operates on committed locked slots)

## Tasks

### 1. Load SortableJS

Add CDN script in `templates/timetable/grid.html` `{% block extra_js %}` (or `base.html` if grid-only). Pin a specific version (not `@latest`). Same pattern as Bootstrap CDN tags.

### 2. Toolbar UI — `templates/timetable/grid.html`

Inside existing admin editor block (`{% if user.is_admin and timetable %}`):

Add buttons:
- **Check Changes** (disabled when `pendingMoves` empty)
- **Publish** (disabled until last check was valid AND no drags since)
- **Discard** (clears pending state)

Pass new URLs via `#timetableEditorConfig` data attributes:
- `data-validate-batch-url`
- `data-publish-url`
- `data-discard-url`

Keep existing move/unlock URLs for unlock flow only.

Add CSS class hooks in `static/css/timetable_grid.css`:
- `.is-pending` — staged, not committed (distinct from `.is-locked`)

### 3. Rewrite drag behavior — `static/js/timetable_editor.js`

**Remove** immediate POST to `moveUrl` on drop.

Implement:
- `pendingMoves = {}` keyed by `slot_id`
- On drop (via SortableJS): update `pendingMoves`, move card in DOM, add `is-pending`, do **not** set `is-locked`
- Re-drag same card overwrites its pending target
- **Check Changes:** POST full `pendingMoves` map to validate-batch endpoint; show violations via `showToast` or inline list; store `change_set_id`; enable Publish only if `is_valid`
- Any drag after successful check → disable Publish until re-check
- **Publish:** POST `change_set_id`; on success, mark cards `is-locked`, clear `pendingMoves`, refresh penalty display from response
- **Discard:** revert all pending cards to `data-original-cell` (extend existing single-card `moveCardBack` to handle full set); POST discard; clear state

Replace native HTML5 `dragstart/drop` listeners with `Sortable.create()` on grid drop zones. Use SortableJS multi-container / group options appropriate for a period×day grid.

### 4. Stop calling MoveSlotView from editor

Editor should not POST to `timetable:move_slot` for normal drags. Leave endpoint for tests/backward compat or remove calls only from JS.

### 5. CSRF

Preserve existing CSRF cookie handling for all new POSTs.

## Out of scope

- Timetable version publish (Prompt 07)
- Non-admin UI changes

## Manual verification

1. Drag 2 cards — query DB mid-session — **no** TimetableSlot changes
2. Check Changes with conflicting pair — see error list
3. Publish after valid check — DB updated
4. Discard — grid reverts, DB unchanged
5. Test drag on narrow viewport / touch if available

## Tests

Extend `timetable/tests.py` or add lightweight JS-independent tests only (backend covered in 06A). At minimum re-run full suite.

## Acceptance criteria

- [ ] No save-on-drop
- [ ] Check/Publish/Discard workflow works in browser
- [ ] SortableJS replaces native DnD
- [ ] Unlock still works
- [ ] `python manage.py test` passes

## Git commit message

```
feat: staged batch timetable editor UI with SortableJS
```
