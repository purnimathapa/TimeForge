from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from core.models import Department, Room, Semester
from academics.models import Subject, Section, TeacherProfile, ClassSession
from scheduling.models import Constraint
from django.db.models import Count

class DashboardView(LoginRequiredMixin, TemplateView):
    def get_template_names(self):
        if self.request.user.role == 'ADMIN':
            return ['dashboard/admin_dashboard.html']
        elif self.request.user.role == 'TEACHER':
            return ['dashboard/teacher_dashboard.html']
        return ['dashboard/base_dashboard.html']  # Fallback just in case

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role = self.request.user.role

        if role == 'ADMIN':
            context['department_count'] = Department.objects.count()
            context['room_count'] = Room.objects.count()
            context['teacher_count'] = TeacherProfile.objects.count()
            context['subject_count'] = Subject.objects.count()
            context['section_count'] = Section.objects.count()
            context['constraint_count'] = Constraint.objects.filter(is_active=True).count()
        
        elif role == 'TEACHER':
            # Add teacher specific context here. 
            # Prompt: "Teacher dashboard: today's sessions (once timetable data exists 
            # — until Prompt 11/12, show an honest empty state, not fake data), a link to their availability settings."
            context['has_timetable'] = False
            
        return context
