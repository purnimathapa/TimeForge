# Deferred Requirements (Post–Prompt 11)

These v2 / gap-analysis items are **intentionally out of scope** for Prompts 01–11. Track them as future prompts only after the core series is green.

## Academic model enrichment

- `SectionOffering` (curriculum unit before scheduling)
- `TeacherSubject` (qualification enforcement)
- `ScheduleRun` (generation audit log: who ran, when, outcome)
- Auto-expand ClassSessions from offerings (lecture + lab split)

## Constraint catalogue (remaining ~28 of 34)

Groups not covered in Prompt 08:

- Identity/uniqueness extras (distinct period validation as explicit rule)
- Room suitability: equipment match, room unavailability windows
- Class group-centred (max daily hours, consecutive periods, required weekly hours hard rule)
- Cross-department spatial (building change gaps, same-floor preference)
- Subject/curriculum (co-requisites, prerequisite ordering)
- Institution policy (break/lunch blocks, observance blackouts, exam periods)
- `CUSTOM` constraint JSON interpreter

Implement using the **handler class pattern** from v2 — one new handler per type, not special cases in the algorithm loop.

## Organisation & scale

- `Building` as first-class optional model (beyond `Room.building` string)
- Teacher **many-to-many** departments
- Block/floor hierarchy



## SaaS & billing

- FR14: subscription / plan status per school
- Tenant self-registration vs operator-provisioned first admin
- Pending-account reminders on admin dashboard



## UX & stack (accepted deviations — change only if product owner requests)

- WeasyPrint instead of reportlab (currently reportlab by design)
- htmx + Alpine.js (forbidden by `.cursorrules`)
- Async generation via Celery/Redis



## Generation & reporting enhancements

- FR7: failure report naming **which constraints** failed (not just `failure_reason` text)
- Department/building filters on institution directory
- CSV export (PDF/XLSX exist today)



## Suggested future prompt numbers


| ID  | Title                                                          |
| --- | -------------------------------------------------------------- |
| 12  | SectionOffering + TeacherSubject + engine qualification checks |
| 13  | ScheduleRun audit + generation history UI                      |
| 14  | Class group constraint group (6 constraints)                   |
| 15  | Institution policy constraints (break/lunch, exam period)      |
| 16  | Building model + spatial constraints                           |
| 17  | Subscription model (FR14)                                      |


