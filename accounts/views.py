from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import User
from .forms import TeacherCreationForm
from .mixins import RoleRequiredMixin
from django.contrib import messages

class TeacherCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = User
    form_class = TeacherCreationForm
    template_name = 'accounts/teacher_form.html'
    success_url = reverse_lazy('home')
    allowed_roles = ['ADMIN']
    
    def form_valid(self, form):
        messages.success(self.request, "Teacher account created successfully.")
        return super().form_valid(form)

class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/profile.html'
