from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from core.models import Department, Room, Semester
from core.forms import SchoolScopedFormMixin
from .models import Subject, Section, TeacherProfile, ClassSession
from scheduling.models import TeacherAvailability


class SubjectForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code', 'credit_hours', 'lecture_hours_per_week', 'lab_hours_per_week', 'description', 'department', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.school is not None:
            self.fields['department'].queryset = Department.objects.filter(
                is_active=True,
                school=self.school,
            )


class SectionForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Section
        fields = ['name', 'year', 'section_label', 'student_count', 'department', 'semester', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.school is not None:
            self.fields['department'].queryset = Department.objects.filter(
                is_active=True,
                school=self.school,
            )
            self.fields['semester'].queryset = Semester.objects.filter(
                is_active=True,
                school=self.school,
            )


class TeacherProfileForm(SchoolScopedFormMixin, forms.ModelForm):
    """Edit an existing teacher profile (account fields are managed separately)."""

    class Meta:
        model = TeacherProfile
        fields = ['employee_id', 'title', 'department', 'max_hours_per_day', 'max_hours_per_week', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.school is not None:
            self.fields['department'].queryset = Department.objects.filter(
                is_active=True,
                school=self.school,
            )


class TeacherCreationForm(UserCreationForm):
    """
    Create a login account and TeacherProfile together in one submit.
    """

    email = forms.EmailField(required=True)
    employee_id = forms.CharField(
        max_length=50,
        help_text="Unique staff identifier (e.g. EMP-101).",
    )
    title = forms.CharField(max_length=50, required=False)
    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        required=False,
    )
    max_hours_per_day = forms.IntegerField(min_value=1, initial=4)
    max_hours_per_week = forms.IntegerField(min_value=1, initial=20)
    is_active = forms.BooleanField(required=False, initial=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        if self.school is not None:
            self.fields['department'].queryset = Department.objects.filter(
                is_active=True,
                school=self.school,
            )

    def clean_employee_id(self):
        employee_id = self.cleaned_data['employee_id']
        qs = TeacherProfile.objects.filter(employee_id=employee_id)
        if self.school is not None:
            qs = qs.filter(user__school=self.school)
        if qs.exists():
            raise ValidationError('A teacher with this employee ID already exists.')
        return employee_id

    def save(self, commit=True):
        with transaction.atomic():
            user = super().save(commit=False)
            user.role = User.RoleChoices.TEACHER
            if self.school is not None:
                user.school = self.school
            user.save()

            profile = TeacherProfile.objects.create(
                user=user,
                employee_id=self.cleaned_data['employee_id'],
                title=self.cleaned_data.get('title', ''),
                department=self.cleaned_data.get('department'),
                max_hours_per_day=self.cleaned_data['max_hours_per_day'],
                max_hours_per_week=self.cleaned_data['max_hours_per_week'],
                is_active=self.cleaned_data.get('is_active', True),
            )
        return profile


class ClassSessionForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = ClassSession
        fields = ['subject', 'teacher', 'section', 'periods_per_week']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.school is not None:
            self.fields['subject'].queryset = Subject.objects.filter(
                is_active=True,
                department__school=self.school,
            )
            self.fields['section'].queryset = Section.objects.filter(
                is_active=True,
                department__school=self.school,
            )
            self.fields['teacher'].queryset = TeacherProfile.objects.filter(
                is_active=True,
                user__school=self.school,
            )


# For Teacher portal
class TeacherAvailabilityForm(forms.ModelForm):
    class Meta:
        model = TeacherAvailability
        fields = ['timeslot', 'is_available']
