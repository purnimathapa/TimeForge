from django import forms
from .models import Subject, Section, TeacherProfile, ClassSession
from scheduling.models import TeacherAvailability

class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code', 'credit_hours', 'lecture_hours_per_week', 'lab_hours_per_week', 'description', 'department', 'is_active']

class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ['name', 'year', 'section_label', 'student_count', 'department', 'semester', 'is_active']

class TeacherProfileForm(forms.ModelForm):
    class Meta:
        model = TeacherProfile
        fields = ['user', 'employee_id', 'title', 'department', 'max_hours_per_day', 'max_hours_per_week', 'is_active']

class ClassSessionForm(forms.ModelForm):
    class Meta:
        model = ClassSession
        fields = ['subject', 'teacher', 'section', 'periods_per_week']

# For Teacher portal
class TeacherAvailabilityForm(forms.ModelForm):
    class Meta:
        model = TeacherAvailability
        fields = ['timeslot', 'is_available']
