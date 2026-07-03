from django import forms
from .models import TimeSlot, Constraint

class TimeSlotForm(forms.ModelForm):
    class Meta:
        model = TimeSlot
        fields = ['day_of_week', 'period_number', 'start_time', 'end_time', 'is_active']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

class ConstraintForm(forms.ModelForm):
    class Meta:
        model = Constraint
        fields = [
            'name', 'constraint_type', 'target_type', 'is_hard', 'weight',
            'semester', 'department', 'teacher', 'room', 'subject', 'section',
            'max_daily_periods', 'required_room_type', 'custom_parameters', 'is_active'
        ]
