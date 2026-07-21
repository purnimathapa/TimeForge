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

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from datetime import timedelta
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
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='published_timetables',
    )
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
        return f"{self.semester.name} · v{self.version} ({self.get_status_display()})"

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
            ('timetable', 'timeslot', 'teacher'),
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


class DraftChangeSet(models.Model):
    """Staged batch of timetable moves awaiting validation and publish."""

    timetable = models.ForeignKey(
        Timetable,
        on_delete=models.CASCADE,
        related_name='draft_change_sets',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    is_valid = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)
    is_discarded = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"DraftChangeSet #{self.pk} for {self.timetable}"


class DraftMove(models.Model):
    """One proposed slot move within a draft change set."""

    change_set = models.ForeignKey(
        DraftChangeSet,
        on_delete=models.CASCADE,
        related_name='moves',
    )
    slot = models.ForeignKey(
        TimetableSlot,
        on_delete=models.CASCADE,
        related_name='draft_moves',
    )
    target_timeslot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE)
    target_room = models.ForeignKey(Room, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('change_set', 'slot')]

    def __str__(self):
        return f"DraftMove slot={self.slot_id} → {self.target_timeslot_id}/{self.target_room_id}"


class TimetableEditLock(models.Model):
    """
    Prevents concurrent admin edits on the same timetable version.

    Locks expire after LOCK_TIMEOUT_MINUTES of inactivity (locked_at is refreshed
    on each successful acquire by the holder). When expired, the next admin to
    mutate steals the lock automatically.
    """

    LOCK_TIMEOUT_MINUTES = 10

    timetable = models.OneToOneField(
        Timetable,
        on_delete=models.CASCADE,
        related_name='edit_lock',
    )
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    locked_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Timetable Edit Lock'
        verbose_name_plural = 'Timetable Edit Locks'

    def __str__(self):
        return f"Lock on {self.timetable} by {self.locked_by}"


def _lock_is_expired(lock):
    expiry = lock.locked_at + timedelta(minutes=TimetableEditLock.LOCK_TIMEOUT_MINUTES)
    return timezone.now() >= expiry


def is_locked_by_other(timetable, user):
    """
    Return True when another user holds a non-expired edit lock on timetable.

    Returns (is_blocked, lock_or_none).
    """
    try:
        lock = timetable.edit_lock
    except TimetableEditLock.DoesNotExist:
        return False, None

    if lock.locked_by_id == user.pk:
        return False, lock
    if _lock_is_expired(lock):
        return False, lock
    return True, lock


def acquire_lock(timetable, user):
    """
    Acquire or refresh the edit lock for timetable.

    Returns (success, lock). On failure, another user holds a non-expired lock.
    Expired locks are stolen by the requesting user.
    """
    with transaction.atomic():
        lock, created = (
            TimetableEditLock.objects
            .select_for_update()
            .get_or_create(
                timetable=timetable,
                defaults={'locked_by': user},
            )
        )
        if created:
            return True, lock

        if lock.locked_by_id == user.pk:
            lock.save(update_fields=['locked_at'])
            return True, lock

        if _lock_is_expired(lock):
            lock.locked_by = user
            lock.save(update_fields=['locked_by', 'locked_at'])
            return True, lock

        return False, lock


def release_lock(timetable):
    """Remove the edit lock after a successful publish or discard."""
    TimetableEditLock.objects.filter(timetable=timetable).delete()


def lock_holder_display_name(lock):
    """Human-readable name for lock holder responses and UI banners."""
    if lock is None:
        return ''
    user = lock.locked_by
    return user.get_full_name() or user.get_username()
