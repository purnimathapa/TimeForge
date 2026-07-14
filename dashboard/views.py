from django.urls import reverse_lazy
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from core.models import Department, Room, Semester
from academics.models import Subject, Section, TeacherProfile, ClassSession
from scheduling.models import Constraint
from django.db.models import Count

class DashboardView(LoginRequiredMixin, TemplateView):
    login_url = reverse_lazy("login")

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
            from timetable.models import Timetable

            context['department_count'] = Department.objects.count()
            context['room_count'] = Room.objects.count()
            context['teacher_count'] = TeacherProfile.objects.count()
            context['subject_count'] = Subject.objects.count()
            context['section_count'] = Section.objects.count()
            context['constraint_count'] = Constraint.objects.filter(is_active=True).count()

            active_semester = Semester.objects.filter(is_active=True).first()
            context['active_semester'] = active_semester
            latest_timetable = None
            if active_semester:
                latest_timetable = (
                    Timetable.objects.filter(semester=active_semester)
                    .order_by('-version')
                    .first()
                )
            context['latest_timetable'] = latest_timetable
            context['has_timetable'] = latest_timetable is not None

        elif role == 'TEACHER':
            from timetable.models import Timetable

            active_semester = Semester.objects.filter(is_active=True).first()
            context['active_semester'] = active_semester
            if active_semester:
                context['has_timetable'] = Timetable.objects.filter(
                    semester=active_semester,
                    status=Timetable.Status.PUBLISHED,
                ).exists()
            else:
                context['has_timetable'] = False
            
        return context
