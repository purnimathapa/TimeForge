from django import forms

from core.models import Department, Room, Session


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
        qs = Department.objects.filter(is_active=True)
        if self.school is not None:
            qs = qs.filter(school=self.school)
        self.fields['department'].queryset = qs.order_by('name')


class SessionForm(SchoolScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Session
        fields = ['name', 'start_date', 'end_date', 'is_active']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
