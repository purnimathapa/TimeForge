# TimeForge — Data Model (Entity List)

Plain-text entity reference mirroring the proposal ERD (Figure 3.2), renamed for Django conventions. This is not ORM code—implementation prompts will translate these into models.

**Naming note:** The proposal entity *Activity* is renamed **ClassSession** to avoid clashing with Django’s built-in `django.contrib.sessions` Session concept.

---

## accounts

### User
Custom auth user (extends Django’s abstract user).
- **Fields:** username, email, password hash, first_name, last_name, is_active, is_staff, date_joined, **role** (admin | scheduler | teacher | viewer)
- **Relationships:** optional OneToOne → Teacher (in academics)

---

## core

### Department
Academic unit that owns subjects, sections, and rooms.
- **Fields:** name, code, description, is_active
- **Relationships:** one-to-many → Subject, Section, Room (optional scoping), Teacher

### Room
Physical space where a class session may be held.
- **Fields:** name, code, building, floor, capacity, room_type (lecture | lab | seminar | computer_lab), is_active
- **Relationships:** optional FK → Department; referenced by TimetableSlot

### Semester
Academic term that bounds offerings and timetable generation.
- **Fields:** name, code, start_date, end_date, is_active
- **Relationships:** one-to-many → SectionOffering, Timetable, Constraint, ScheduleRun

---

## academics

### Subject
Course or module taught within a department.
- **Fields:** code, name, credit_hours, lecture_hours_per_week, lab_hours_per_week, description, is_active
- **Relationships:** FK → Department; one-to-many → TeacherSubject, SectionOffering, ClassSession

### Section
Student cohort (e.g., batch/year group) within a department for a semester.
- **Fields:** name, code, student_count, is_active
- **Relationships:** FK → Department; FK → Semester; one-to-many → SectionOffering

### Teacher
Instructor profile linked to a user account.
- **Fields:** employee_id, title, max_hours_per_week, is_active
- **Relationships:** OneToOne → User; FK → Department; one-to-many → TeacherSubject, SectionOffering (as assigned teacher), TimetableSlot

### TeacherSubject
Qualification mapping: which subjects a teacher is allowed to teach.
- **Fields:** (none beyond keys)
- **Relationships:** FK → Teacher; FK → Subject
- **Constraints:** unique together (teacher, subject)

### SectionOffering
A subject assigned to a section for a specific semester—the unit of work the scheduler must place.
- **Fields:** sessions_per_week, preferred_session_length (in time-slot units), notes
- **Relationships:** FK → Section; FK → Subject; FK → Semester; optional FK → Teacher (preferred/assigned instructor); one-to-many → ClassSession
- **Constraints:** unique together (section, subject, semester)

---

## scheduling

### TimeSlot
Atomic period in the weekly grid (proposal: timeslot / period).
- **Fields:** day_of_week (Mon–Sun), start_time, end_time, period_number, label, is_active
- **Relationships:** one-to-many → TimetableSlot; used by Constraint rules that reference periods

### ClassSession
Schedulable teaching activity derived from a section offering (proposal: Activity).
- **Fields:** session_type (lecture | lab | tutorial), duration_slots (how many consecutive TimeSlots), sequence_number (e.g., lecture 1 of 3), is_locked (manual override flag)
- **Relationships:** FK → SectionOffering; one-to-many → TimetableSlot
- **Notes:** One SectionOffering may expand into multiple ClassSession rows (e.g., 2 lectures + 1 lab)

### Constraint
Hard or soft rule the engine must respect or penalize (proposal: Constraint).
- **Fields:** name, constraint_type (teacher_unavailable | room_type_required | max_daily_hours | no_adjacent_gaps | custom), is_hard, weight (for soft constraints), parameters (JSON: day, time range, room_type, etc.), is_active
- **Relationships:** FK → Semester; optional FK → Department (scope); optional FK → Teacher; optional FK → Room; optional FK → Subject

### ScheduleRun
Audit record of a timetable generation attempt (proposal: generation job / run log).
- **Fields:** started_at, finished_at, status (pending | running | success | failed | partial), algorithm_version, parameters (JSON), conflict_count, message
- **Relationships:** FK → Semester; optional FK → Department; optional FK → Timetable (result); FK → User (triggered_by)

---

## timetable

### Timetable
Header for a generated or manually edited schedule for a scope (proposal: Timetable).
- **Fields:** name, version, status (draft | published | archived), generated_at, published_at, notes
- **Relationships:** FK → Semester; optional FK → Department; one-to-many → TimetableSlot; optional reverse FK from ScheduleRun

### TimetableSlot
Placement of one ClassSession on the grid (proposal: TimetableSlot / assignment).
- **Fields:** is_manual (True if editor moved it), notes
- **Relationships:** FK → Timetable; FK → ClassSession; FK → TimeSlot; FK → Room; FK → Teacher (denormalized from ClassSession/offering for query speed)
- **Constraints:** no double-booking of Room + TimeSlot within same Timetable; no double-booking of Teacher + TimeSlot within same Timetable

---

## dashboard

No persistent entities. The dashboard app queries aggregates from User, Timetable, TimetableSlot, ClassSession, and ScheduleRun.

---

## Entity Relationship Summary

```
User ────────────── OneToOne ────────────── Teacher
  │                                            │
  │                                            ├── TeacherSubject ── Subject
  │                                            │
Department ──┬── Subject ──┬── SectionOffering ──┬── ClassSession
             │             │         │           │
             ├── Section ──┘         │           │
             │                       Semester    │
             └── Room                 │         │
                                       │         │
TimeSlot ◄──────────────── TimetableSlot ────────┘
              │                │
              │                ├── Timetable
              │                └── Room
              │
Constraint ─── Semester
ScheduleRun ── Semester, Timetable, User
```

---

## Proposal ERD (Figure 3.2) → Django Name Mapping

| Proposal entity   | Django entity      | App          |
|-------------------|--------------------|--------------|
| User              | User               | accounts     |
| Department        | Department         | core         |
| Room              | Room               | core         |
| Semester          | Semester           | core         |
| Subject / Course  | Subject            | academics    |
| Section / Batch   | Section            | academics    |
| Teacher           | Teacher            | academics    |
| TeacherCourse     | TeacherSubject     | academics    |
| CourseOffering    | SectionOffering    | academics    |
| TimeSlot / Period | TimeSlot           | scheduling   |
| Activity          | **ClassSession**   | scheduling   |
| Constraint        | Constraint         | scheduling   |
| GenerationJob     | ScheduleRun        | scheduling   |
| Timetable         | Timetable          | timetable    |
| TimetableSlot     | TimetableSlot      | timetable    |

---

## Integrity Rules (Business Level)

1. A published Timetable must have only TimetableSlot rows belonging to its Semester’s offerings.
2. ClassSession rows are created from SectionOffering before generation; the engine only assigns TimeSlot + Room.
3. Teacher on TimetableSlot must be qualified via TeacherSubject for the offering’s Subject (enforced in engine + optional DB checks).
4. Room.room_type must satisfy Constraint and Subject session_type (e.g., lab → lab or computer_lab).
5. Deleting a Semester is blocked if published Timetable records exist (soft-archive instead).
