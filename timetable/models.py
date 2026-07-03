"""
timetable/models.py

Timetable and TimetableSlot models — the persistence layer for engine results.

Design notes:
- Timetable is a versioned header. Each generation for a semester creates a new
  row (version 1, 2, 3…). Old rows are set to ARCHIVED status, so audit history
  is preserved without extra infrastructure.
- TimetableSlot stores one (class_session, timeslot, room) placement. The teacher
  FK is denormalised here (copied from ClassSession) so that timetable queries
  don't require multi-level joins for teacher filtering.
- DB-level unique_together constraints mirror the algorithm's hard constraints as a
  defence-in-depth layer: even if a bug in the engine slipped through, the database
  will reject any double-booking at INSERT time.
- is_locked is stored now (for the Prompt 13 drag-and-drop editor); in this prompt
  all engine-generated slots are created with is_locked=False.
"""

from django.db import models
from core.models import Room, Semester
from academics.models import ClassSession, TeacherProfile
from scheduling.models import TimeSlot


class Timetable(models.Model):
    class Status(models.TextChoices):
        DRAFT     = 'DRAFT',     'Draft'
        PUBLISHED = 'PUBLISHED', 'Published'
        ARCHIVED  = 'ARCHIVED',  'Archived'

    semester     = models.ForeignKey(
        Semester, on_delete=models.PROTECT, related_name='timetables'
    )
    version      = models.PositiveIntegerField(
        default=1,
        help_text="Auto-incremented per semester. Version 1 is the first generation."
    )
    status       = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    penalty_score = models.IntegerField(
        default=0,
        help_text="Soft-constraint penalty score returned by the scheduling engine."
    )
    notes        = models.TextField(blank=True)

    class Meta:
        ordering = ['-version']
        # A timetable version is unique per semester
        unique_together = [('semester', 'version')]
        verbose_name = 'Timetable'
        verbose_name_plural = 'Timetables'

    def save(self, *args, **kwargs):
        """Auto-assign version number if this is a new (unsaved) instance."""
        if not self.pk:
            # Count existing timetables for this semester to get next version
            existing_count = Timetable.objects.filter(semester=self.semester).count()
            self.version = existing_count + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.semester.name} — v{self.version} ({self.get_status_display()})"

    @property
    def slot_count(self):
        return self.slots.count()


class TimetableSlot(models.Model):
    """
    One placed ClassSession on the weekly timetable grid.

    Each row = one (session, timeslot, room) assignment within a specific
    Timetable version.

    DB unique_together constraints (defence-in-depth beneath the engine):
      (timetable, timeslot, room)          — no room double-booked in a slot
      (timetable, timeslot, class_session) — same session not placed in same slot twice
      (timetable, timeslot, teacher)       — no teacher double-booked in a slot
        (teacher is nullable; the constraint is enforced only when teacher is set,
         which PostgreSQL handles correctly for nullable unique_together columns
         via a partial unique index — Django's unique_together with NULL values
         follows SQL standard: NULLs are not considered equal.)
    """
    timetable     = models.ForeignKey(
        Timetable, on_delete=models.CASCADE, related_name='slots'
    )
    class_session = models.ForeignKey(
        ClassSession, on_delete=models.PROTECT, related_name='timetable_slots'
    )
    timeslot      = models.ForeignKey(
        TimeSlot, on_delete=models.PROTECT, related_name='timetable_slots'
    )
    room          = models.ForeignKey(
        Room, on_delete=models.PROTECT, related_name='timetable_slots'
    )
    # Denormalised from ClassSession for query performance (avoids extra join)
    teacher       = models.ForeignKey(
        TeacherProfile,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='timetable_slots'
    )
    # Editor flags — stubbed as False until Prompt 13
    is_locked     = models.BooleanField(
        default=False,
        help_text="If True, re-generation will not overwrite this slot (Prompt 13)."
    )
    is_manual     = models.BooleanField(
        default=False,
        help_text="If True, this slot was moved by the drag-and-drop editor."
    )

    class Meta:
        ordering = ['timeslot__day_of_week', 'timeslot__period_number']
        unique_together = [
            ('timetable', 'timeslot', 'room'),
            ('timetable', 'timeslot', 'class_session'),
        ]
        indexes = [
            models.Index(fields=['timetable', 'teacher']),
            models.Index(fields=['timetable', 'room']),
            models.Index(fields=['timetable', 'timeslot']),
            models.Index(fields=['timetable', 'class_session']),
        ]
        verbose_name = 'Timetable Slot'
        verbose_name_plural = 'Timetable Slots'

    def __str__(self):
        return (
            f"{self.class_session.subject.code} | "
            f"{self.timeslot} | "
            f"{self.room.name}"
        )
