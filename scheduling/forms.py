from django import forms

from academics.models import Section, Subject, TeacherProfile
from core.models import Department, Room, Semester
from core.forms import SchoolScopedFormMixin
from .models import TimeSlot, Constraint


class TimeSlotForm(forms.ModelForm):
    class Meta:
        model = TimeSlot
        fields = ['day_of_week', 'period_number', 'start_time', 'end_time', 'is_active']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }


class ConstraintForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Constraint
        fields = [
            'name', 'constraint_type', 'target_type', 'is_hard', 'weight',
            'semester', 'department', 'teacher', 'room', 'subject', 'section',
            'max_daily_periods', 'max_consecutive_periods', 'required_room_type',
            'custom_parameters', 'is_active',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.school is None:
            return

        self.fields['semester'].queryset = Semester.objects.filter(
            is_active=True,
            school=self.school,
        )
        self.fields['department'].queryset = Department.objects.filter(
            is_active=True,
            school=self.school,
        )
        self.fields['teacher'].queryset = TeacherProfile.objects.filter(
            is_active=True,
            user__school=self.school,
        )
        self.fields['room'].queryset = Room.objects.filter(
            is_active=True,
            school=self.school,
        )
        self.fields['subject'].queryset = Subject.objects.filter(
            is_active=True,
            department__school=self.school,
        )
        self.fields['section'].queryset = Section.objects.filter(
            is_active=True,
            department__school=self.school,
        )
