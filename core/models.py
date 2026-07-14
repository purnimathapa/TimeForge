from django.db import models
from django.core.exceptions import ValidationError


class School(models.Model):
    name = models.CharField(max_length=200, unique=True)
    code = models.SlugField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Department(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name='departments',
    )
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.code})"


class Room(models.Model):
    class RoomType(models.TextChoices):
        LECTURE = 'LECTURE', 'Lecture'
        LAB = 'LAB', 'Laboratory'
        SEMINAR = 'SEMINAR', 'Seminar'
        COMPUTER_LAB = 'COMPUTER_LAB', 'Computer Lab'

    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name='rooms',
    )
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    building = models.CharField(max_length=100, blank=True)
    floor = models.CharField(max_length=20, blank=True)
    capacity = models.PositiveIntegerField()
    room_type = models.CharField(max_length=20, choices=RoomType.choices, default=RoomType.LECTURE)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rooms',
        help_text="Optional informational link; tenant ownership is via school.",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.get_room_type_display()})"


class Semester(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name='semesters',
    )
    name = models.CharField(max_length=100)  # e.g. Fall 2026
    code = models.CharField(max_length=20, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)

    def clean(self):
        if self.is_active:
            active_semesters = Semester.objects.filter(is_active=True, school=self.school)
            if self.pk:
                active_semesters = active_semesters.exclude(pk=self.pk)
            if active_semesters.exists():
                raise ValidationError({"is_active": "Only one semester can be active at a time."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
