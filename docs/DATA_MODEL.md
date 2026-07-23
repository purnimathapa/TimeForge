# TimeForge — Data Model (Entity List)

Implementation-oriented entity reference for the Course / Session restructure.
**Naming note:** Calendar windows are `core.Session`. Schedulable activities remain `academics.ClassSession` (proposal *Activity*).

---

## accounts

### User
Custom auth user (extends Django’s abstract user).
- **Fields:** username, email, password hash, first_name, last_name, is_active, is_staff, date_joined, **role** (admin | teacher | class_rep)
- **Relationships:** optional OneToOne → TeacherProfile / ClassRepProfile; optional FK → School

---

## core

### Department
Academic unit that owns courses, subjects, and rooms.
- **Fields:** name, code, description, is_active
- **Relationships:** FK → School; one-to-many → Course, Room; M2M ← Subject, TeacherProfile

### Room
Physical space where a class may be held.
- **Fields:** name, code, building, floor, capacity, room_type, is_active
- **Relationships:** FK → School; optional FK → Department; referenced by TimetableSlot

### Session
School-wide academic calendar window (start/end dates) shared by all departments and courses.
- **Fields:** name, start_date, end_date, is_active (one active per school)
- **Relationships:** FK → School; one-to-many → ClassSession, Timetable, Constraint

---

## academics

### Subject
Module taught within one or more departments.
- **Fields:** code, name, credit_hours, lecture/lab hours, description, is_active
- **Relationships:** M2M → Department; one-to-many → ClassSession

### Course
Degree / program catalog entry (e.g. BE in Computer Engineering).
- **Fields:** name, code, is_active
- **Relationships:** FK → Department; one-to-many → CourseLevel (levels 1–8 auto-created on save)

### CourseLevel
Study level within a course (1–8) — the schedulable cohort unit.
- **Fields:** level (1–8), student_count, is_active
- **Relationships:** FK → Course; one-to-many → ClassSession, ClassRepProfile

### TeacherProfile
Instructor profile linked to a user account.
- **Fields:** employee_id, title, max hours, is_visiting, is_active
- **Relationships:** OneToOne → User; M2M → Department; one-to-many → ClassSession, TimetableSlot

### ClassRepProfile
Class representative for a CourseLevel.
- **Relationships:** OneToOne → User; FK → CourseLevel

### ClassSession
Schedulable teaching activity for a CourseLevel in a Session.
- **Fields:** periods_per_week
- **Relationships:** FK → Session; FK → CourseLevel; FK → Subject; optional FK → Teacher; one-to-many → TimetableSlot

---

## scheduling

### TimeSlot
Atomic period in the weekly grid.
- **Fields:** day_of_week, period_number, start_time, end_time, is_active

### Constraint
Hard or soft rule scoped to a Session.
- **Relationships:** FK → Session; optional FK → Department, Teacher, Room, Subject, CourseLevel

---

## timetable

### Timetable
Versioned schedule header for a Session.
- **Relationships:** FK → Session; one-to-many → TimetableSlot

### TimetableSlot
Placement of one ClassSession on the grid.
- **Relationships:** FK → Timetable, ClassSession, TimeSlot, Room; optional denormalized Teacher

---

## Entity Relationship Summary

```
School ── Session ──┬── ClassSession ── TimetableSlot ── Timetable
                    │         │
                    │         ├── Subject
                    │         ├── TeacherProfile
                    │         └── CourseLevel ── Course ── Department
                    │
                    └── Constraint
```

---

## Proposal ERD → Django Name Mapping

| Proposal entity   | Django entity      | App          |
|-------------------|--------------------|--------------|
| Semester          | Session            | core         |
| Section / Batch   | Course + CourseLevel | academics  |
| Subject / Course  | Subject            | academics    |
| Activity          | ClassSession       | academics    |
| Timetable         | Timetable          | timetable    |

---

## Integrity Rules (Business Level)

1. Only one Session may be active per school.
2. Each Course has CourseLevels 1–8.
3. ClassSession rows belong to a Session and a CourseLevel; the engine assigns TimeSlot + Room.
4. Deleting a Session is blocked if Timetable rows still reference it (PROTECT).
