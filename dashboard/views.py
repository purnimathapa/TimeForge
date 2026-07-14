from django.urls import reverse_lazy
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from core.models import Department, Room, Semester
from core.tenant import filter_by_school, school_filter
from academics.models import Subject, Section, TeacherProfile
from scheduling.models import Constraint


class DashboardView(LoginRequiredMixin, TemplateView):
    login_url = reverse_lazy("accounts:login")

    def get_template_names(self):
        if self.request.user.role == 'ADMIN':
            return ['dashboard/admin_dashboard.html']
        elif self.request.user.role == 'TEACHER':
            return ['dashboard/teacher_dashboard.html']
        elif self.request.user.role == 'CLASS_REP':
            return ['dashboard/class_rep_dashboard.html']
        return ['dashboard/base_dashboard.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role = self.request.user.role
        request = self.request

        if role == 'ADMIN':
            from timetable.models import Timetable

            context['department_count'] = school_filter(Department.objects.all(), request).count()
            context['room_count'] = school_filter(Room.objects.all(), request).count()
            context['teacher_count'] = filter_by_school(
                TeacherProfile.objects.all(), request, 'user__school'
            ).count()
            context['subject_count'] = filter_by_school(
                Subject.objects.all(), request, 'department__school'
            ).count()
            context['section_count'] = filter_by_school(
                Section.objects.all(), request, 'department__school'
            ).count()
            context['constraint_count'] = filter_by_school(
                Constraint.objects.filter(is_active=True), request, 'semester__school'
            ).count()

            active_semester = school_filter(
                Semester.objects.filter(is_active=True), request
            ).first()
            context['active_semester'] = active_semester
            latest_timetable = None
            if active_semester:
                latest_timetable = (
                    Timetable.objects.filter(semester=active_semester)
                    .order_by('-version')
                    .first()
                )
                context['published_timetable'] = (
                    Timetable.objects.filter(
                        semester=active_semester,
                        status=Timetable.Status.PUBLISHED,
                    )
                    .order_by('-version')
                    .first()
                )
            context['latest_timetable'] = latest_timetable
            context['has_timetable'] = latest_timetable is not None

        elif role in ('TEACHER', 'CLASS_REP'):
            from timetable.models import Timetable

            active_semester = school_filter(
                Semester.objects.filter(is_active=True), request
            ).first()
            context['active_semester'] = active_semester
            if active_semester:
                context['has_timetable'] = Timetable.objects.filter(
                    semester=active_semester,
                    status=Timetable.Status.PUBLISHED,
                ).exists()
            else:
                context['has_timetable'] = False

            if role == 'CLASS_REP':
                profile = getattr(self.request.user, 'class_rep_profile', None)
                context['class_rep_profile'] = profile
                context['section'] = profile.section if profile else None

        return context
