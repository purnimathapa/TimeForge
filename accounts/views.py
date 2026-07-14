from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from accounts.mixins import RoleRequiredMixin
from .forms import AdminCreationForm
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

    def form_valid(self, form):
        messages.success(
            self.request,
            f"Admin account '{form.cleaned_data['username']}' created successfully.",
        )
        return super().form_valid(form)
