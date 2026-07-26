from django import forms

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Fieldset, Layout

from academics.models import CourseLevel, Subject, TeacherProfile
from core.models import Department, Room, Session
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
    """Admin-friendly constraint editor.

    Wraps the raw model fields in a guided layout: only the parameter fields
    relevant to the selected rule type are shown (progressive disclosure), and
    "Preferred Teaching Time" is captured through friendly day/period pickers
    instead of hand-written JSON.
    """

    preferred_days = forms.MultipleChoiceField(
        choices=TimeSlot.DayOfWeek.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Preferred days",
        help_text="Days the teacher prefers to teach.",
    )
    period_start = forms.IntegerField(
        min_value=1,
        required=False,
        label="Earliest preferred period",
    )
    period_end = forms.IntegerField(
        min_value=1,
        required=False,
        label="Latest preferred period",
    )

    class Meta:
        model = Constraint
        fields = [
            'name', 'constraint_type', 'target_type', 'is_hard',
            'session', 'department', 'teacher', 'room', 'subject', 'course_level',
            'max_daily_periods', 'max_weekly_periods', 'max_consecutive_periods',
            'required_room_type', 'is_active',
        ]
        help_texts = {
            'name': "A short label, e.g. \"No Friday afternoons for Dr. Rai\".",
            'is_hard': "Hard rules must never be broken. Soft rules are preferences the engine tries to honour.",
            'target_type': "Who or what this rule applies to.",
            'max_daily_periods': "Maximum teaching periods allowed in one day.",
            'max_weekly_periods': "Maximum teaching periods allowed across the whole week.",
        }
        labels = {
            'max_daily_periods': 'Max daily periods',
            'max_weekly_periods': 'Max weekly periods',
            'max_consecutive_periods': 'Max consecutive periods',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        session_qs = Session.objects.all()
        department_qs = Department.objects.filter(is_active=True)
        teacher_qs = TeacherProfile.objects.filter(is_active=True)
        room_qs = Room.objects.filter(is_active=True)
        subject_qs = Subject.objects.filter(is_active=True)
        course_level_qs = CourseLevel.objects.filter(
            is_active=True,
            course__is_active=True,
        ).select_related('course')

        if self.school is not None:
            session_qs = session_qs.filter(school=self.school)
            department_qs = department_qs.filter(school=self.school)
            teacher_qs = teacher_qs.filter(user__school=self.school)
            room_qs = room_qs.filter(school=self.school)
            subject_qs = subject_qs.filter(departments__school=self.school).distinct()
            course_level_qs = course_level_qs.filter(
                course__department__school=self.school,
            )

        self.fields['session'].queryset = session_qs.order_by('-is_active', '-start_date')
        self.fields['department'].queryset = department_qs.order_by('name')
        self.fields['teacher'].queryset = teacher_qs.select_related('user')
        self.fields['room'].queryset = room_qs.order_by('name')
        self.fields['subject'].queryset = subject_qs.order_by('code')
        self.fields['course_level'].queryset = course_level_qs.order_by(
            'course__name', 'level',
        )

        # Pre-fill the friendly Preferred Teaching Time inputs when editing.
        instance = getattr(self, 'instance', None)
        if instance and instance.pk and instance.custom_parameters and (
            instance.constraint_type == Constraint.ConstraintType.PREFERRED_TEACHING_TIME
        ):
            params = instance.custom_parameters or {}
            self.fields['preferred_days'].initial = [str(d) for d in params.get('preferred_days', [])]
            self.fields['period_start'].initial = params.get('period_start')
            self.fields['period_end'].initial = params.get('period_end')

        # New rules default to soft preferences except room-type (always hard).
        if not getattr(instance, 'pk', None):
            self.fields['is_hard'].initial = False

        self.helper = self._build_helper()

    def _build_helper(self):
        helper = FormHelper()
        helper.form_tag = False  # base template supplies <form> and buttons
        helper.disable_csrf = True
        helper.layout = Layout(
            Fieldset(
                "Basics",
                "name",
                "constraint_type",
                "is_hard",
                "is_active",
            ),
            Fieldset(
                "Applies to",
                "session",
                "target_type",
                Div("teacher", css_id="tgt-teacher"),
                Div("course_level", css_id="tgt-course-level"),
                Div("room", css_id="tgt-room"),
                Div("subject", css_id="tgt-subject"),
                Div("department", css_id="tgt-department"),
            ),
            Fieldset(
                "Parameters",
                Div("max_daily_periods", css_id="param-max-daily"),
                Div("max_weekly_periods", css_id="param-max-weekly"),
                Div("max_consecutive_periods", css_id="param-max-consec"),
                Div("required_room_type", css_id="param-room-type"),
                Div(
                    HTML(
                        '<p class="text-muted small mb-2">The teacher prefers to teach on '
                        'these days, within this period range.</p>'
                    ),
                    "preferred_days",
                    "period_start",
                    "period_end",
                    css_id="param-preferred",
                ),
            ),
        )
        return helper

    def clean(self):
        cleaned = super().clean()
        ctype = cleaned.get('constraint_type')

        if ctype == Constraint.ConstraintType.ROOM_TYPE_REQUIRED:
            # Room type is applied as a hard filter on activity placement.
            cleaned['is_hard'] = True
            cleaned['target_type'] = Constraint.TargetType.SUBJECT
            if not cleaned.get('subject'):
                self.add_error('subject', "Room Type Required must target a subject.")

        if ctype in {
            Constraint.ConstraintType.MAX_WEEKLY_PERIODS,
            Constraint.ConstraintType.MAX_CONSECUTIVE_PERIODS,
            Constraint.ConstraintType.PREFERRED_TEACHING_TIME,
        }:
            target = cleaned.get('target_type')
            if target not in {Constraint.TargetType.TEACHER, Constraint.TargetType.GLOBAL}:
                self.add_error(
                    'target_type',
                    "This rule type applies to a teacher or globally to all teachers.",
                )
            if target == Constraint.TargetType.TEACHER and not cleaned.get('teacher'):
                self.add_error('teacher', "Select the teacher this rule applies to.")

        if ctype == Constraint.ConstraintType.MAX_DAILY_PERIODS:
            target = cleaned.get('target_type')
            if target not in {
                Constraint.TargetType.TEACHER,
                Constraint.TargetType.COURSE_LEVEL,
                Constraint.TargetType.GLOBAL,
            }:
                self.add_error(
                    'target_type',
                    "Max Daily Periods can target a teacher, a course level, or all teachers.",
                )
            if target == Constraint.TargetType.TEACHER and not cleaned.get('teacher'):
                self.add_error('teacher', "Select the teacher this rule applies to.")
            if target == Constraint.TargetType.COURSE_LEVEL and not cleaned.get('course_level'):
                self.add_error('course_level', "Select the course level this rule applies to.")

        if ctype == Constraint.ConstraintType.NO_ADJACENT_GAPS:
            target = cleaned.get('target_type')
            if target not in {
                Constraint.TargetType.TEACHER,
                Constraint.TargetType.COURSE_LEVEL,
                Constraint.TargetType.GLOBAL,
            }:
                self.add_error(
                    'target_type',
                    "No Adjacent Gaps can target a teacher, a course level, or all teachers.",
                )
            if target == Constraint.TargetType.TEACHER and not cleaned.get('teacher'):
                self.add_error('teacher', "Select the teacher this rule applies to.")
            if target == Constraint.TargetType.COURSE_LEVEL and not cleaned.get('course_level'):
                self.add_error('course_level', "Select the course level this rule applies to.")

        if ctype == Constraint.ConstraintType.PREFERRED_TEACHING_TIME:
            days = cleaned.get('preferred_days') or []
            period_start = cleaned.get('period_start')
            period_end = cleaned.get('period_end')

            if not days:
                self.add_error('preferred_days', "Select at least one preferred day.")
            if period_start is None:
                self.add_error('period_start', "Enter the earliest preferred period.")
            if period_end is None:
                self.add_error('period_end', "Enter the latest preferred period.")
            if period_start is not None and period_end is not None and period_start > period_end:
                self.add_error('period_end', "Latest period must be greater than or equal to the earliest.")

            if not self.has_error('preferred_days') and not self.has_error('period_start') \
                    and not self.has_error('period_end'):
                params = {
                    'preferred_days': [int(d) for d in days],
                    'period_start': period_start,
                    'period_end': period_end,
                }
                # custom_parameters is not a form field, so set it on the instance
                # before ModelForm._post_clean() runs model.full_clean().
                cleaned['custom_parameters'] = params
                self.instance.custom_parameters = params

        cleaned['weight'] = Constraint.DEFAULT_SOFT_WEIGHT
        self.instance.weight = Constraint.DEFAULT_SOFT_WEIGHT
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.weight = Constraint.DEFAULT_SOFT_WEIGHT
        if self.cleaned_data.get('constraint_type') == Constraint.ConstraintType.PREFERRED_TEACHING_TIME:
            instance.custom_parameters = self.cleaned_data.get('custom_parameters')
        elif instance.constraint_type != Constraint.ConstraintType.PREFERRED_TEACHING_TIME:
            instance.custom_parameters = None
        if commit:
            instance.save()
            self.save_m2m()
        return instance
