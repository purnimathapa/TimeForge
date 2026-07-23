from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from core.models import Department, Session


class Subject(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20)
    credit_hours = models.DecimalField(max_digits=4, decimal_places=2, default=3.0)
    lecture_hours_per_week = models.PositiveIntegerField(default=3)
    lab_hours_per_week = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)
    departments = models.ManyToManyField(
        Department,
        related_name='subjects',
        blank=False,
        help_text='A subject may be offered by one or more departments.',
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def department_names(self):
        names = list(self.departments.values_list('name', flat=True))
        return ', '.join(names) if names else 'No department'


class Course(models.Model):
    """Degree / program catalog entry (e.g. BE in Computer Engineering)."""

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30)
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name='courses',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('code', 'department')
        ordering = ['name']

    def __str__(self):
        return f"{self.code} — {self.name}"

    def ensure_levels(self):
        """Create CourseLevel rows 1–8 if missing."""
        existing = set(self.levels.values_list('level', flat=True))
        to_create = [
            CourseLevel(course=self, level=level)
            for level in range(1, 9)
            if level not in existing
        ]
        if to_create:
            CourseLevel.objects.bulk_create(to_create)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.ensure_levels()


class CourseLevel(models.Model):
    """Study level (semester 1–8) within a Course — the schedulable cohort unit."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='levels')
    level = models.PositiveSmallIntegerField(
        choices=[(i, f'Semester {i}') for i in range(1, 9)],
    )
    student_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('course', 'level')
        ordering = ['course__name', 'level']

    def __str__(self):
        return f"{self.course.code} · Sem {self.level}"

    @property
    def display_name(self):
        return f"{self.course.name} — Semester {self.level}"


class TeacherProfile(models.Model):
    class Title(models.TextChoices):
        # Ordered from most senior to most junior academic rank.
        PROF_DR = 'Prof. Dr.', 'Prof. Dr.'
        PROFESSOR = 'Professor', 'Professor'
        ASSOCIATE_PROFESSOR = 'Associate Professor', 'Associate Professor'
        ASSISTANT_PROFESSOR = 'Assistant Professor', 'Assistant Professor'
        DR = 'Dr.', 'Dr.'
        LECTURER = 'Lecturer', 'Lecturer'
        ASSISTANT_LECTURER = 'Assistant Lecturer', 'Assistant Lecturer'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teacher_profile')
    employee_id = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=50, blank=True, choices=Title.choices)
    is_visiting = models.BooleanField(
        default=False,
        help_text="Tick if this is visiting / guest faculty.",
    )
    departments = models.ManyToManyField(
        Department,
        related_name='teachers',
        blank=True,
        help_text='A teacher may be affiliated with one or more departments.',
    )
    max_hours_per_day = models.PositiveIntegerField(default=4)
    max_hours_per_week = models.PositiveIntegerField(default=20)
    is_active = models.BooleanField(default=True)

    EMPLOYEE_ID_PREFIX = 'EMP-'

    @classmethod
    def generate_employee_id(cls):
        """Return the next unused employee ID (EMP-0001, EMP-0002, …)."""
        prefix = cls.EMPLOYEE_ID_PREFIX
        max_n = 0
        for eid in cls.objects.filter(employee_id__startswith=prefix).values_list('employee_id', flat=True):
            suffix = eid[len(prefix):]
            if suffix.isdigit():
                max_n = max(max_n, int(suffix))

        for _ in range(1000):
            max_n += 1
            candidate = f'{prefix}{max_n:04d}'
            if not cls.objects.filter(employee_id=candidate).exists():
                return candidate
        raise RuntimeError('Unable to allocate a unique employee ID.')

    @property
    def display_name(self):
        """Human name for the teacher, falling back to the username."""
        return self.user.get_full_name().strip() or self.user.get_username()

    @property
    def ranked_name(self):
        """Title + name, e.g. 'Dr. Jane Doe' (no employee number)."""
        title = f"{self.title} " if self.title else ""
        return f"{title}{self.display_name}".strip()

    @property
    def department_names(self):
        names = list(self.departments.values_list('name', flat=True))
        return ', '.join(names) if names else 'No department'

    def __str__(self):
        return self.ranked_name


class ClassRepProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='class_rep_profile',
    )
    course_level = models.ForeignKey(
        CourseLevel,
        on_delete=models.CASCADE,
        related_name='class_reps',
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.course_level})"


class ClassSession(models.Model):
    """
    The schedulable teaching activity (unplaced) for a CourseLevel in a Session.
    """
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name='class_sessions',
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='class_sessions')
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='class_sessions',
    )
    course_level = models.ForeignKey(
        CourseLevel,
        on_delete=models.CASCADE,
        related_name='class_sessions',
    )
    periods_per_week = models.PositiveIntegerField(default=1)

    def clean(self):
        from scheduling.models import TimeSlot
        total_slots = TimeSlot.objects.filter(is_active=True).count()
        if total_slots > 0 and self.periods_per_week > total_slots:
            raise ValidationError({
                "periods_per_week": (
                    f"Cannot exceed the total number of active time slots in a week ({total_slots})."
                ),
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        teacher_name = self.teacher.user.get_full_name() if self.teacher else "Unassigned"
        return f"{self.subject.code} - {self.course_level} ({teacher_name})"
