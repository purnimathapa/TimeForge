from django.contrib.auth.forms import UserCreationForm
from .models import User
from django import forms

class TeacherCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')
        
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.RoleChoices.TEACHER
        if commit:
            user.save()
        return user
