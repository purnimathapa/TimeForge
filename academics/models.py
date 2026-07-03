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
class ClassSession(models.Model):
    """
    The schedulable teaching activity (unplaced).
    Derived from a SectionOffering / Subject for a Section.
    """
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='class_sessions')
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='class_sessions')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='class_sessions')
    periods_per_week = models.PositiveIntegerField(default=1)
    
    def clean(self):
        from scheduling.models import TimeSlot
        # Ensure periods_per_week doesn't exceed total available timeslots
        total_slots = TimeSlot.objects.filter(is_active=True).count()
        if total_slots > 0 and self.periods_per_week > total_slots:
            raise ValidationError({
                "periods_per_week": f"Cannot exceed the total number of active time slots in a week ({total_slots})."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        teacher_name = self.teacher.user.get_full_name() if self.teacher else "Unassigned"
        return f"{self.subject.code} - {self.section.name} ({teacher_name})"


