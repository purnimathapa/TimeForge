from django import forms

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Fieldset, Layout

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
            'name', 'constraint_type', 'target_type', 'is_hard', 'weight',
            'semester', 'department', 'teacher', 'room', 'subject', 'section',
            'max_daily_periods', 'max_consecutive_periods', 'required_room_type',
            'custom_parameters', 'is_active',
        ]
        widgets = {
            'custom_parameters': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': '{"key": "value"}',
            }),
        }
        help_texts = {
            'name': "A short label, e.g. \"No Friday afternoons for Dr. Rai\".",
            'is_hard': "Hard rules must never be broken. Soft rules are preferences the engine tries to honour.",
            'weight': "Only used for soft rules. Higher weight means the engine tries harder to satisfy it.",
            'target_type': "Who or what this rule applies to.",
            'custom_parameters': "Advanced: JSON parameters, only for Custom rules.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.school is not None:
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

        # Pre-fill the friendly Preferred Teaching Time inputs when editing.
        instance = getattr(self, 'instance', None)
        if instance and instance.pk and instance.custom_parameters and (
            instance.constraint_type == Constraint.ConstraintType.PREFERRED_TEACHING_TIME
        ):
            params = instance.custom_parameters or {}
            self.fields['preferred_days'].initial = [str(d) for d in params.get('preferred_days', [])]
            self.fields['period_start'].initial = params.get('period_start')
            self.fields['period_end'].initial = params.get('period_end')

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
                Div("weight", css_id="field-weight"),
            ),
            Fieldset(
                "Applies to",
                "semester",
                "target_type",
                Div("teacher", css_id="tgt-teacher"),
                Div("section", css_id="tgt-section"),
                Div("room", css_id="tgt-room"),
                Div("subject", css_id="tgt-subject"),
                Div("department", css_id="tgt-department"),
            ),
            Fieldset(
                "Parameters",
                Div("max_daily_periods", css_id="param-max-daily"),
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
                Div("custom_parameters", css_id="param-custom"),
                Field("is_active"),
            ),
        )
        return helper

    def clean(self):
        cleaned = super().clean()
        ctype = cleaned.get('constraint_type')

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
                cleaned['custom_parameters'] = {
                    'preferred_days': [int(d) for d in days],
                    'period_start': period_start,
                    'period_end': period_end,
                }

        return cleaned
