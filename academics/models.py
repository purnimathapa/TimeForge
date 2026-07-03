from django.db import models
from django.conf import settings
from core.models import Department, Semester

class Subject(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20)
    credit_hours = models.DecimalField(max_digits=4, decimal_places=2, default=3.0)
    lecture_hours_per_week = models.PositiveIntegerField(default=3)
    lab_hours_per_week = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='subjects')
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('code', 'department')

    def __str__(self):
        return f"{self.code} - {self.name}"

class Section(models.Model):
    name = models.CharField(max_length=100) # e.g. "CS Batch 2023 A"
    year = models.PositiveIntegerField() # e.g. 1, 2, 3, 4
    section_label = models.CharField(max_length=10) # e.g. "A", "B"
    student_count = models.PositiveIntegerField(default=0)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='sections')
    semester = models.ForeignKey(Semester, on_delete=models.PROTECT, related_name='sections')
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('name', 'semester')

    def __str__(self):
        return f"{self.name} ({self.semester.name})"

class TeacherProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teacher_profile')
    employee_id = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=50, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='teachers')
    max_hours_per_day = models.PositiveIntegerField(default=4)
    max_hours_per_week = models.PositiveIntegerField(default=20)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title} {self.user.get_full_name()} ({self.employee_id})"

# Schema decision: A relational model TeacherAvailability per day/period is much cleaner 
# than a JSON blob because it allows database-level querying (e.g. finding all teachers available on Monday morning), 
# enables proper foreign key relationships to time periods (if we add them later),
# and is easier to validate using Django forms/admin without custom JSON parsing logic.
class TeacherAvailability(models.Model):
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 1, 'Monday'
        TUESDAY = 2, 'Tuesday'
        WEDNESDAY = 3, 'Wednesday'
        THURSDAY = 4, 'Thursday'
        FRIDAY = 5, 'Friday'
        SATURDAY = 6, 'Saturday'
        SUNDAY = 7, 'Sunday'

    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='availabilities')
    day_of_week = models.IntegerField(choices=DayOfWeek.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Teacher availabilities"

    def __str__(self):
        return f"{self.teacher} on {self.get_day_of_week_display()} ({self.start_time} - {self.end_time})"
