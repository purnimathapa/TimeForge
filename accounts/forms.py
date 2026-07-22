from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class AdminCreationForm(UserCreationForm):
    """Create a login account with the Admin role."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.RoleChoices.ADMIN
        if self.school is not None:
            user.school = self.school
        if commit:
            user.save()
        return user
