from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction

from academics.models import ClassRepProfile, Section
from .models import User


class AdminCreationForm(UserCreationForm):
    """Create a login account with the Admin role."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.RoleChoices.ADMIN
        if commit:
            user.save()
        return user


class ClassRepCreationForm(UserCreationForm):
    """Create a login account and ClassRepProfile in one submit."""

    section = forms.ModelChoiceField(
        queryset=Section.objects.filter(is_active=True),
        help_text="The section this class representative represents.",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def save(self, commit=True):
        with transaction.atomic():
            user = super().save(commit=False)
            user.role = User.RoleChoices.CLASS_REP
            user.save()
            ClassRepProfile.objects.create(
                user=user,
                section=self.cleaned_data['section'],
                is_active=True,
            )
        return user
