from django import forms

from core.models import Department, Room, Semester
from core.tenant import school_filter


class SchoolScopedFormMixin:
    """Pass school into ModelChoiceField querysets."""

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)


class DepartmentForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code', 'description', 'is_active']


class RoomForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Room
        fields = ['name', 'code', 'building', 'floor', 'capacity', 'room_type', 'department', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.school is not None:
            self.fields['department'].queryset = Department.objects.filter(
                is_active=True,
                school=self.school,
            )


class SemesterForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Semester
        fields = ['name', 'code', 'start_date', 'end_date', 'is_active']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
