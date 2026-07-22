# TimeForge — Cursor Prompt Series

Use these prompts **in order**. Each prompt is scoped so Cursor can finish in one session without hallucinating. Do not skip ahead — later prompts assume earlier phases are merged, migrated, and tested.

## Ground truth (read before every prompt)

- **Stack:** Django + PostgreSQL + server-rendered templates + Bootstrap 5 (see `.cursorrules`).
- **Engine path:** `scheduling/engine/` (not `scheduling/services/`).
- **Roles today:** `ADMIN`, `TEACHER` (+ `CLASS_REP` after Prompt 05).
- **Docs under `docs/ARCHITECTURE.md`, `DATA_MODEL.md`:** older plan — **do not refactor code to match them**. Update docs after each prompt to reflect what you built.
- **After each prompt:** run `python manage.py test`, fix failures, then commit.

## Prompt order

**Before each prompt, paste this header into Cursor:**

```
You are working on the existing TimeForge Django project.
Read .cursorrules and docs/cursor-prompts/README.md.
Implement ONLY the attached prompt — do not skip ahead or refactor unrelated code.
Run python manage.py test before finishing. Update docs/ if your changes obsolete them.
```

| # | File | Est. size | Depends on |
|---|------|-----------|------------|
| 01 | [01-security-hygiene.md](./01-security-hygiene.md) | S | — |
| 02 | [02-bug-fixes.md](./02-bug-fixes.md) | S | 01 |
| 03 | [03-teacher-read-access.md](./03-teacher-read-access.md) | M | 02 |
| 04 | [04-admin-account-creation.md](./04-admin-account-creation.md) | S | 03 |
| 05 | [05-class-representative-role.md](./05-class-representative-role.md) | M | 04 |
| 06A | [06a-batch-editor-backend.md](./06a-batch-editor-backend.md) | L | 05 |
| 06B | [06b-batch-editor-frontend.md](./06b-batch-editor-frontend.md) | L | 06A |
| 07 | [07-timetable-publish-workflow.md](./07-timetable-publish-workflow.md) | M | 06B |
| 08 | [08-teacher-constraints.md](./08-teacher-constraints.md) | M | 07 |
| 09A | [09a-multitenancy-models.md](./09a-multitenancy-models.md) | L | 08 |
| 09B | [09b-multitenancy-scoping.md](./09b-multitenancy-scoping.md) | XL | 09A |
| 09C | [09c-multitenancy-tests.md](./09c-multitenancy-tests.md) | M | 09B |
| 10 | [10-my-routine-mobile-ux.md](./10-my-routine-mobile-ux.md) | M | 07 |
| 11 | [11-editor-lock-schema.md](./11-editor-lock-schema.md) | S | 06B |

**Note:** Prompt 10 (My Routine) can run in parallel with 08–09 **after Prompt 07** if you prefer UX work while tenancy is in progress. Prompts 09A–09C must stay sequential.

## v2 requirements coverage

| Requirement | Prompt(s) |
|-------------|-----------|
| Security / no leaked credentials | 01 |
| Teacher institution read access | 03 |
| Admin-issued accounts (Admin, Teacher, CR) | 04, 05 |
| Batch editor (stage → check → publish moves) | 06A, 06B |
| Official timetable publish (DRAFT → PUBLISHED) | 07 |
| Teacher-centred constraints (partial catalogue) | 08 |
| Multi-tenancy (School) | 09A–09C |
| My Routine / mobile viewer UX | 10 |
| Editor concurrency lock | 11 |

**Deferred (intentionally not in this series):** see [BACKLOG.md](./BACKLOG.md) — full 34-constraint catalogue, `CUSTOM` evaluation, `SectionOffering`/`TeacherSubject`, `ScheduleRun`, subscription/billing (FR14), Building entity, htmx/Alpine, WeasyPrint.
