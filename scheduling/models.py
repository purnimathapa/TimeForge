from django.db import models
from core.models import Department, Room, Session
from academics.models import TeacherProfile, Subject, CourseLevel
from django.core.exceptions import ValidationError

class TimeSlot(models.Model):
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 1, 'Monday'
        TUESDAY = 2, 'Tuesday'
        WEDNESDAY = 3, 'Wednesday'
        THURSDAY = 4, 'Thursday'
        FRIDAY = 5, 'Friday'

    day_of_week = models.IntegerField(choices=DayOfWeek.choices)
    period_number = models.PositiveIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('day_of_week', 'period_number')
        ordering = ['day_of_week', 'period_number']

    def __str__(self):
        return f"{self.get_day_of_week_display()} - Period {self.period_number} ({self.start_time.strftime('%H:%M')} to {self.end_time.strftime('%H:%M')})"

class TeacherAvailability(models.Model):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='availabilities')
    timeslot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, related_name='teacher_availabilities')
    is_available = models.BooleanField(default=True)

    class Meta:
        unique_together = ('teacher', 'timeslot')
        verbose_name_plural = "Teacher availabilities"

    def __str__(self):
        return f"{self.teacher} availability for {self.timeslot}"

# Schema decision for Constraint target FKs:
# Instead of using a GenericForeignKey, we use specific nullable ForeignKeys for the targets.
# Tradeoff: GenericForeignKey is more flexible and requires fewer columns.
# However, nullable FKs are type-safe, allow standard ORM reverse relationships, 
# preserve referential integrity at the database level (ON DELETE cascades), and make
# JOIN queries significantly faster and easier to write.
class Constraint(models.Model):
    class ConstraintType(models.TextChoices):
        ROOM_TYPE_REQUIRED = 'ROOM_TYPE_REQUIRED', 'Room Type Required'
        MAX_DAILY_PERIODS = 'MAX_DAILY_PERIODS', 'Max Daily Periods'
        MAX_WEEKLY_PERIODS = 'MAX_WEEKLY_PERIODS', 'Max Weekly Periods'
        NO_ADJACENT_GAPS = 'NO_ADJACENT_GAPS', 'No Adjacent Gaps'
        MAX_CONSECUTIVE_PERIODS = 'MAX_CONSECUTIVE_PERIODS', 'Max Consecutive Periods'
        PREFERRED_TEACHING_TIME = 'PREFERRED_TEACHING_TIME', 'Preferred Teaching Time'

    class TargetType(models.TextChoices):
        TEACHER = 'TEACHER', 'Teacher'
        COURSE_LEVEL = 'COURSE_LEVEL', 'Course Level'
        ROOM = 'ROOM', 'Room'
        SUBJECT = 'SUBJECT', 'Subject'
        GLOBAL = 'GLOBAL', 'Global / Session'

    name = models.CharField(max_length=150)
    constraint_type = models.CharField(max_length=50, choices=ConstraintType.choices)
    target_type = models.CharField(max_length=20, choices=TargetType.choices)
    is_hard = models.BooleanField(default=True)
    # Soft constraints all use the same internal weight for engine scoring.
    DEFAULT_SOFT_WEIGHT = 10
    weight = models.PositiveIntegerField(
        default=DEFAULT_SOFT_WEIGHT,
        help_text="Internal soft-constraint weight (always 10; not shown in the UI).",
    )
    
    # Nullable explicit FKs for targets
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='constraints')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, null=True, blank=True)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True)
    course_level = models.ForeignKey(CourseLevel, on_delete=models.CASCADE, null=True, blank=True)

    # Structured Parameter Fields
    max_daily_periods = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum teaching periods allowed in one day (Max Daily Periods).",
    )
    max_weekly_periods = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum teaching periods allowed across the week (Max Weekly Periods).",
    )
    max_consecutive_periods = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Used for MAX_CONSECUTIVE_PERIODS",
    )
    required_room_type = models.CharField(max_length=20, choices=Room.RoomType.choices, null=True, blank=True, help_text="Used for ROOM_TYPE_REQUIRED")
    
    # Fallback for preferred teaching time parameters
    custom_parameters = models.JSONField(
        null=True,
        blank=True,
        help_text=(
            "Used for PREFERRED_TEACHING_TIME. "
            "Shape: "
            '{"preferred_days": [1, 2], "period_start": 1, "period_end": 4} '
            "where preferred_days uses TimeSlot day codes (1=Monday … 5=Friday)."
        ),
    )
    
    is_active = models.BooleanField(default=True)

    def clean(self):
        if self.constraint_type == self.ConstraintType.MAX_DAILY_PERIODS and self.max_daily_periods is None:
            raise ValidationError({"max_daily_periods": "Required when constraint type is Max Daily Periods."})
        if self.constraint_type == self.ConstraintType.MAX_WEEKLY_PERIODS and self.max_weekly_periods is None:
            raise ValidationError({"max_weekly_periods": "Required when constraint type is Max Weekly Periods."})
        if self.constraint_type == self.ConstraintType.MAX_CONSECUTIVE_PERIODS and self.max_consecutive_periods is None:
            raise ValidationError({
                "max_consecutive_periods": "Required when constraint type is Max Consecutive Periods.",
            })
        if self.constraint_type == self.ConstraintType.ROOM_TYPE_REQUIRED and not self.required_room_type:
            raise ValidationError({"required_room_type": "Required when constraint type is Room Type Required."})
        if self.constraint_type == self.ConstraintType.PREFERRED_TEACHING_TIME:
            params = self.custom_parameters or {}
            preferred_days = params.get("preferred_days")
            period_start = params.get("period_start")
            period_end = params.get("period_end")
            # Use non-field errors so ModelForm can surface them even though
            # custom_parameters is not an editable form field.
            if not preferred_days:
                raise ValidationError("Select at least one preferred day.")
            if period_start is None or period_end is None:
                raise ValidationError("Earliest and latest preferred periods are required.")
            if period_start > period_end:
                raise ValidationError("Latest period must be greater than or equal to the earliest.")

    def save(self, *args, **kwargs):
        self.weight = self.DEFAULT_SOFT_WEIGHT
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_constraint_type_display()})"
