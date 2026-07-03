from django import forms
from .models import Department, Room, Semester
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code', 'description', 'is_active']

class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['name', 'code', 'building', 'floor', 'capacity', 'room_type', 'department', 'is_active']

class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester
        fields = ['name', 'code', 'start_date', 'end_date', 'is_active']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
