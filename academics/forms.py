from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from core.models import Department, Session
from core.forms import SchoolScopedFormMixin
from .models import (
    Subject, Course, CourseLevel, CourseLevelOffering,
    TeacherProfile, ClassRepProfile, ClassSession,
)
from scheduling.models import TeacherAvailability


LEVEL_CHOICES = [(i, f'Semester {i}') for i in range(1, 9)]


def _department_checkbox_field(*, required):
    return forms.ModelMultipleChoiceField(
        queryset=Department.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=required,
        label='Departments',
        help_text='Select every department this record belongs to.',
    )


def _resolve_course_level(course, level):
    """Return the CourseLevel for course+level, creating it if missing."""
    if course is None or level is None:
        return None
    course_level, _ = CourseLevel.objects.get_or_create(
        course=course,
        level=level,
        defaults={'is_active': True},
    )
    return course_level


class SubjectForm(SchoolScopedFormMixin, forms.ModelForm):
    departments = _department_checkbox_field(required=True)

    class Meta:
        model = Subject
        fields = [
            'name', 'code', 'credit_hours', 'lecture_hours_per_week',
            'lab_hours_per_week', 'description', 'departments', 'is_active',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Department.objects.filter(is_active=True)
        if self.school is not None:
            qs = qs.filter(school=self.school)
        self.fields['departments'].queryset = qs.order_by('name')

    def clean_departments(self):
        departments = self.cleaned_data.get('departments')
        if not departments:
            raise ValidationError('Select at least one department.')
        school_ids = {dept.school_id for dept in departments}
        if len(school_ids) > 1:
            raise ValidationError('All selected departments must belong to the same school.')
        return departments

    def clean(self):
        cleaned = super().clean()
        code = cleaned.get('code')
        departments = cleaned.get('departments')
        if code and departments:
            school_ids = {dept.school_id for dept in departments}
            qs = Subject.objects.filter(
                code=code,
                departments__school_id__in=school_ids,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('code', 'A subject with this code already exists in this school.')
        return cleaned


class CourseForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Course
        fields = ['name', 'code', 'department', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Department.objects.filter(is_active=True)
        if self.school is not None:
            qs = qs.filter(school=self.school)
        self.fields['department'].queryset = qs.order_by('name')


class RunningSemesterForm(forms.Form):
    """Create a CourseLevelOffering for a course in the active session."""

    level = forms.TypedChoiceField(
        choices=LEVEL_CHOICES,
        coerce=int,
        label='Semester',
        help_text='Study level (1–8) to mark as running in the active session.',
    )
    shift = forms.ChoiceField(
        choices=CourseLevelOffering.Shift.choices,
        initial=CourseLevelOffering.Shift.DAY,
        label='Shift',
    )

    def __init__(self, *args, course=None, session=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.course = course
        self.session = session
        self.fields['level'].widget.attrs.update({'class': 'form-select'})
        self.fields['shift'].widget.attrs.update({'class': 'form-select'})
        if course is not None and session is not None:
            taken = set(
                CourseLevelOffering.objects.filter(
                    session=session,
                    course_level__course=course,
                ).values_list('course_level__level', flat=True)
            )
            self.fields['level'].choices = [
                (i, f'Semester {i}') for i in range(1, 9) if i not in taken
            ]

    def clean(self):
        cleaned = super().clean()
        if self.course is None or self.session is None:
            raise ValidationError('Course and active session are required.')
        level = cleaned.get('level')
        if level is None:
            return cleaned
        if not self.fields['level'].choices:
            raise ValidationError('All semesters are already running for this course.')
        if CourseLevelOffering.objects.filter(
            session=self.session,
            course_level__course=self.course,
            course_level__level=level,
        ).exists():
            raise ValidationError({'level': 'That semester is already running.'})
        return cleaned

    def save(self):
        course_level = _resolve_course_level(self.course, self.cleaned_data['level'])
        return CourseLevelOffering.objects.create(
            session=self.session,
            course_level=course_level,
            shift=self.cleaned_data['shift'],
        )


class OfferingShiftForm(forms.ModelForm):
    class Meta:
        model = CourseLevelOffering
        fields = ['shift']
        widgets = {
            'shift': forms.Select(attrs={'class': 'form-select'}),
        }


class TeacherProfileForm(SchoolScopedFormMixin, forms.ModelForm):
    """Edit an existing teacher profile, including the account's name."""

    first_name = forms.CharField(max_length=150, required=False, label="First name")
    last_name = forms.CharField(max_length=150, required=False, label="Last name")
    employee_id = forms.CharField(
        required=False,
        disabled=True,
        label="Employee ID",
        help_text="Assigned automatically and cannot be changed.",
    )
    departments = _department_checkbox_field(required=False)

    field_order = [
        'first_name', 'last_name', 'employee_id', 'title', 'is_visiting',
        'departments', 'max_periods_per_day', 'is_active',
    ]

    class Meta:
        model = TeacherProfile
        fields = [
            'title', 'is_visiting', 'departments',
            'max_periods_per_day', 'is_active',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.user_id:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['employee_id'].initial = self.instance.employee_id
        qs = Department.objects.filter(is_active=True)
        if self.school is not None:
            qs = qs.filter(school=self.school)
        self.fields['departments'].queryset = qs.order_by('name')

    def clean_departments(self):
        departments = self.cleaned_data.get('departments')
        if departments:
            school_ids = {dept.school_id for dept in departments}
            if len(school_ids) > 1:
                raise ValidationError('All selected departments must belong to the same school.')
        return departments

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        if commit:
            user.save()
            profile.save()
            self.save_m2m()
        return profile


class TeacherCreationForm(UserCreationForm):
    """
    Create a login account and TeacherProfile together in one submit.
    Employee ID is allocated automatically.
    """

    first_name = forms.CharField(max_length=150, required=True, label="First name")
    last_name = forms.CharField(max_length=150, required=False, label="Last name")
    email = forms.EmailField(required=True)
    title = forms.ChoiceField(
        choices=[('', 'Select a title')] + list(TeacherProfile.Title.choices),
        required=False,
        label="Title / rank",
    )
    is_visiting = forms.BooleanField(
        required=False,
        initial=False,
        label="Visiting faculty",
    )
    departments = _department_checkbox_field(required=False)
    max_periods_per_day = forms.IntegerField(
        min_value=1,
        initial=4,
        label='Max periods per day',
        help_text='Maximum teaching periods this teacher may have in one day.',
    )
    is_active = forms.BooleanField(required=False, initial=True)

    field_order = [
        'first_name', 'last_name', 'username', 'email', 'password1', 'password2',
        'title', 'is_visiting', 'departments',
        'max_periods_per_day', 'is_active',
    ]

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        qs = Department.objects.filter(is_active=True)
        if self.school is not None:
            qs = qs.filter(school=self.school)
        self.fields['departments'].queryset = qs.order_by('name')

    def clean_departments(self):
        departments = self.cleaned_data.get('departments')
        if departments:
            school_ids = {dept.school_id for dept in departments}
            if len(school_ids) > 1:
                raise ValidationError('All selected departments must belong to the same school.')
        return departments

    def save(self, commit=True):
        with transaction.atomic():
            user = super().save(commit=False)
            user.role = User.RoleChoices.TEACHER
            if self.school is not None:
                user.school = self.school
            user.save()

            profile = TeacherProfile.objects.create(
                user=user,
                employee_id=TeacherProfile.generate_employee_id(),
                title=self.cleaned_data.get('title', ''),
                is_visiting=self.cleaned_data.get('is_visiting', False),
                max_periods_per_day=self.cleaned_data['max_periods_per_day'],
                is_active=self.cleaned_data.get('is_active', True),
            )
            profile.departments.set(self.cleaned_data.get('departments') or [])
        return profile


class ClassRepProfileForm(SchoolScopedFormMixin, forms.ModelForm):
    """Edit an existing class representative profile, including the account's name."""

    first_name = forms.CharField(max_length=150, required=False, label="First name")
    last_name = forms.CharField(max_length=150, required=False, label="Last name")
    email = forms.EmailField(required=False)
    course = forms.ModelChoiceField(
        queryset=Course.objects.none(),
        label='Course',
        help_text='The degree program this class representative represents.',
    )
    level = forms.TypedChoiceField(
        choices=LEVEL_CHOICES,
        coerce=int,
        label='Level',
        help_text='Semester / study level within the course (1–8).',
    )

    field_order = ['first_name', 'last_name', 'email', 'course', 'level', 'is_active']

    class Meta:
        model = ClassRepProfile
        fields = ['is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.user_id:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['email'].initial = self.instance.user.email
        course_qs = Course.objects.filter(is_active=True)
        if self.school is not None:
            course_qs = course_qs.filter(department__school=self.school)
        self.fields['course'].queryset = course_qs.order_by('name')
        if self.instance and self.instance.pk and self.instance.course_level_id:
            self.fields['course'].initial = self.instance.course_level.course_id
            self.fields['level'].initial = self.instance.course_level.level

    def clean(self):
        cleaned = super().clean()
        course = cleaned.get('course')
        level = cleaned.get('level')
        if course and level is not None:
            cleaned['course_level'] = _resolve_course_level(course, level)
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.course_level = self.cleaned_data['course_level']
        user = profile.user
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        user.email = self.cleaned_data.get('email', '')
        if commit:
            user.save()
            profile.save()
        return profile


class ClassRepCreationForm(UserCreationForm):
    """Create a login account and ClassRepProfile together in one submit."""

    first_name = forms.CharField(max_length=150, required=True, label="First name")
    last_name = forms.CharField(max_length=150, required=False, label="Last name")
    email = forms.EmailField(required=True)
    course = forms.ModelChoiceField(
        queryset=Course.objects.none(),
        label='Course',
        help_text='The degree program this class representative represents.',
    )
    level = forms.TypedChoiceField(
        choices=LEVEL_CHOICES,
        coerce=int,
        label='Level',
        help_text='Semester / study level within the course (1–8).',
    )
    is_active = forms.BooleanField(required=False, initial=True)

    field_order = [
        'first_name', 'last_name', 'username', 'email',
        'password1', 'password2', 'course', 'level', 'is_active',
    ]

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        course_qs = Course.objects.filter(is_active=True)
        if self.school is not None:
            course_qs = course_qs.filter(department__school=self.school)
        self.fields['course'].queryset = course_qs.order_by('name')

    def clean(self):
        cleaned = super().clean()
        course = cleaned.get('course')
        level = cleaned.get('level')
        if course and level is not None:
            cleaned['course_level'] = _resolve_course_level(course, level)
        return cleaned

    def save(self, commit=True):
        with transaction.atomic():
            user = super().save(commit=False)
            user.role = User.RoleChoices.CLASS_REP
            if self.school is not None:
                user.school = self.school
            user.save()
            profile = ClassRepProfile.objects.create(
                user=user,
                course_level=self.cleaned_data['course_level'],
                is_active=self.cleaned_data.get('is_active', True),
            )
        return profile


class ClassSessionForm(SchoolScopedFormMixin, forms.ModelForm):
    course = forms.ModelChoiceField(
        queryset=Course.objects.none(),
        label='Course',
    )
    level = forms.TypedChoiceField(
        choices=LEVEL_CHOICES,
        coerce=int,
        label='Level',
        help_text='Semester / study level within the course (1–8).',
    )

    class Meta:
        model = ClassSession
        fields = ['session', 'subject', 'teacher', 'periods_per_week']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # List all sessions for the school (not only active) so edits of past
        # sessions still work; active sessions sort first.
        session_qs = Session.objects.all()
        subject_qs = Subject.objects.filter(is_active=True)
        teacher_qs = TeacherProfile.objects.filter(is_active=True)
        course_qs = Course.objects.filter(is_active=True)

        if self.school is not None:
            session_qs = session_qs.filter(school=self.school)
            subject_qs = subject_qs.filter(departments__school=self.school).distinct()
            teacher_qs = teacher_qs.filter(user__school=self.school)
            course_qs = course_qs.filter(department__school=self.school)

        self.fields['session'].queryset = session_qs.order_by('-is_active', '-start_date')
        self.fields['subject'].queryset = subject_qs.order_by('code')
        self.fields['teacher'].queryset = teacher_qs.select_related('user').order_by(
            'user__first_name', 'user__last_name',
        )
        self.fields['course'].queryset = course_qs.order_by('name')

        if self.instance and self.instance.pk and self.instance.course_level_id:
            self.fields['course'].initial = self.instance.course_level.course_id
            self.fields['level'].initial = self.instance.course_level.level

    def clean(self):
        cleaned = super().clean()
        course = cleaned.get('course')
        level = cleaned.get('level')
        if course and level is not None:
            cleaned['course_level'] = _resolve_course_level(course, level)
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.course_level = self.cleaned_data['course_level']
        if commit:
            instance.save()
        return instance


# For Teacher portal
class TeacherAvailabilityForm(forms.ModelForm):
    class Meta:
        model = TeacherAvailability
        fields = ['timeslot', 'is_available']
