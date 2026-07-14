from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from accounts.mixins import RoleRequiredMixin
from .forms import AdminCreationForm, ClassRepCreationForm
from .models import User


def custom_logout(request):
    logout(request)
    return redirect('accounts:login')


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/profile.html'


class AdminCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    allowed_roles = ['ADMIN']
    model = User
    form_class = AdminCreationForm
    template_name = 'accounts/admin_form.html'
    success_url = reverse_lazy('home')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['school'] = getattr(self.request, 'school', None)
        return kwargs

    def form_valid(self, form):
        messages.success(
            self.request,
            f"Admin account '{form.cleaned_data['username']}' created successfully.",
        )
        return super().form_valid(form)


class ClassRepCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    allowed_roles = ['ADMIN']
    model = User
    form_class = ClassRepCreationForm
    template_name = 'accounts/class_rep_form.html'
    success_url = reverse_lazy('home')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['school'] = getattr(self.request, 'school', None)
        return kwargs

    def form_valid(self, form):
        messages.success(
            self.request,
            (
                f"Class representative account '{form.cleaned_data['username']}' "
                f"created for section {form.cleaned_data['section']}."
            ),
        )
        return super().form_valid(form)
