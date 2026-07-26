from django.urls import reverse_lazy, reverse
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.db.models import Q
from django.contrib import messages
from accounts.mixins import RoleRequiredMixin
from core.mixins import SchoolFormMixin, ProtectedDeleteMixin
from core.models import Session
from core.tenant import filter_by_school
from .models import (
    Subject, Course, CourseLevelOffering, TeacherProfile, ClassRepProfile, ClassSession,
)
from scheduling.models import TeacherAvailability
from .forms import (
    SubjectForm,
    CourseForm,
    RunningSemesterForm,
    OfferingShiftForm,
    TeacherProfileForm,
    TeacherCreationForm,
    ClassRepProfileForm,
    ClassRepCreationForm,
    ClassSessionForm,
)

ACADEMICS_SCHOOL_LOOKUPS = {
    Subject: 'departments__school',
    Course: 'department__school',
    TeacherProfile: 'user__school',
    ClassRepProfile: 'user__school',
    ClassSession: 'course_level__course__department__school',
}


class AcademicsAdminCRUDMixin(SchoolFormMixin, RoleRequiredMixin):
    allowed_roles = ['ADMIN']
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        lookup = ACADEMICS_SCHOOL_LOOKUPS.get(self.model)
        if lookup:
            qs = filter_by_school(qs, self.request, lookup).distinct()
        return qs

# -- Subject --
class SubjectListView(AcademicsAdminCRUDMixin, ListView):
    model = Subject
    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('departments')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        return qs

class SubjectCreateView(AcademicsAdminCRUDMixin, CreateView):
    model = Subject
    form_class = SubjectForm
    success_url = reverse_lazy('academics:subject_list')
    def form_valid(self, form):
        messages.success(self.request, "Subject created successfully.")
        return super().form_valid(form)

class SubjectUpdateView(AcademicsAdminCRUDMixin, UpdateView):
    model = Subject
    form_class = SubjectForm
    success_url = reverse_lazy('academics:subject_list')
    def form_valid(self, form):
        messages.success(self.request, "Subject updated successfully.")
        return super().form_valid(form)

class SubjectDeleteView(ProtectedDeleteMixin, AcademicsAdminCRUDMixin, DeleteView):
    model = Subject
    success_url = reverse_lazy('academics:subject_list')
    success_message = "Subject deleted successfully."

# -- Course --
class CourseListView(AcademicsAdminCRUDMixin, ListView):
    model = Course
    template_name = 'academics/course_list.html'

    def get_queryset(self):
        qs = super().get_queryset().select_related('department')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        return qs

class CourseCreateView(AcademicsAdminCRUDMixin, CreateView):
    model = Course
    form_class = CourseForm
    template_name = 'academics/course_form.html'
    success_url = reverse_lazy('academics:course_list')

    def form_valid(self, form):
        messages.success(self.request, "Course created successfully.")
        return super().form_valid(form)

class CourseUpdateView(AcademicsAdminCRUDMixin, UpdateView):
    model = Course
    form_class = CourseForm
    template_name = 'academics/course_form.html'
    success_url = reverse_lazy('academics:course_list')

    def form_valid(self, form):
        messages.success(self.request, "Course updated successfully.")
        return super().form_valid(form)

class CourseDeleteView(ProtectedDeleteMixin, AcademicsAdminCRUDMixin, DeleteView):
    model = Course
    template_name = 'academics/course_confirm_delete.html'
    success_url = reverse_lazy('academics:course_list')
    success_message = "Course deleted successfully."


class CourseDetailView(AcademicsAdminCRUDMixin, DetailView):
    """
    Course hub: pick a running semester for the active session, set Morning/Day
    shift, list subjects/teachers, and link to that cohort's timetable.
    """
    model = Course
    template_name = 'academics/course_detail.html'
    context_object_name = 'course'

    def get_queryset(self):
        return super().get_queryset().select_related('department')

    def _active_session(self):
        qs = Session.objects.filter(is_active=True)
        school = getattr(self.request.user, 'school', None)
        if school is not None:
            qs = qs.filter(school=school)
        return qs.first()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        course = self.object
        session = self._active_session()
        ctx['active_session'] = session
        ctx['offerings'] = []
        ctx['selected_offering'] = None
        ctx['class_sessions'] = []
        ctx['create_form'] = None
        ctx['shift_form'] = None

        if session is None:
            return ctx

        offerings = list(
            CourseLevelOffering.objects.filter(
                session=session,
                course_level__course=course,
            )
            .select_related('course_level')
            .order_by('course_level__level')
        )
        ctx['offerings'] = offerings
        ctx['create_form'] = RunningSemesterForm(course=course, session=session)

        if not offerings:
            return ctx

        selected_id = self.request.GET.get('offering')
        selected = None
        if selected_id:
            selected = next((o for o in offerings if str(o.pk) == str(selected_id)), None)
        if selected is None:
            selected = offerings[0]
        ctx['selected_offering'] = selected
        ctx['shift_form'] = OfferingShiftForm(instance=selected)
        ctx['class_sessions'] = list(
            ClassSession.objects.filter(
                session=session,
                course_level=selected.course_level,
            )
            .select_related('subject', 'teacher__user')
            .order_by('subject__code')
        )
        return ctx


class RunningSemesterCreateView(AcademicsAdminCRUDMixin, View):
    """POST: add a running semester (CourseLevelOffering) for a course."""

    http_method_names = ['post']

    def post(self, request, pk):
        course = get_object_or_404(
            filter_by_school(Course.objects.all(), request, 'department__school'),
            pk=pk,
        )
        session = Session.objects.filter(is_active=True)
        if getattr(request.user, 'school', None) is not None:
            session = session.filter(school=request.user.school)
        session = session.first()
        if session is None:
            messages.error(request, "Set an active session before adding a running semester.")
            return redirect('academics:course_detail', pk=course.pk)

        form = RunningSemesterForm(request.POST, course=course, session=session)
        if form.is_valid():
            offering = form.save()
            messages.success(
                request,
                f"Semester {offering.course_level.level} is now running "
                f"({offering.get_shift_display()}).",
            )
            return redirect(
                f"{reverse('academics:course_detail', kwargs={'pk': course.pk})}"
                f"?offering={offering.pk}"
            )
        for err in form.non_field_errors():
            messages.error(request, err)
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
        return redirect('academics:course_detail', pk=course.pk)


class OfferingShiftUpdateView(AcademicsAdminCRUDMixin, View):
    """POST: update Morning/Day shift for a running semester."""

    http_method_names = ['post']

    def post(self, request, pk):
        offering = get_object_or_404(
            filter_by_school(
                CourseLevelOffering.objects.select_related('course_level__course'),
                request,
                'course_level__course__department__school',
            ),
            pk=pk,
        )
        form = OfferingShiftForm(request.POST, instance=offering)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Semester {offering.course_level.level} shift set to "
                f"{offering.get_shift_display()}.",
            )
        else:
            messages.error(request, "Could not update shift.")
        return redirect(
            f"{reverse('academics:course_detail', kwargs={'pk': offering.course_level.course_id})}"
            f"?offering={offering.pk}"
        )


# -- TeacherProfile --
class TeacherListView(AcademicsAdminCRUDMixin, ListView):
    model = TeacherProfile
    template_name = 'academics/teacher_list.html'
    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('departments')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(employee_id__icontains=q))
        return qs


class TeacherDetailView(AcademicsAdminCRUDMixin, DetailView):
    """Admin hub for one teacher: load, subjects, classes, availability summary."""

    model = TeacherProfile
    template_name = 'academics/teacher_detail.html'
    context_object_name = 'teacher'

    def get_queryset(self):
        return super().get_queryset().select_related('user').prefetch_related('departments')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        teacher = self.object

        session_qs = Session.objects.filter(is_active=True)
        school = getattr(self.request.user, 'school', None)
        if school is not None:
            session_qs = session_qs.filter(school=school)
        session = session_qs.first()
        ctx['active_session'] = session

        class_sessions = ClassSession.objects.filter(teacher=teacher)
        if session is not None:
            class_sessions = class_sessions.filter(session=session)
        class_sessions = (
            class_sessions
            .select_related(
                'subject',
                'session',
                'course_level',
                'course_level__course',
            )
            .order_by('course_level__course__code', 'course_level__level', 'subject__code')
        )
        ctx['class_sessions'] = list(class_sessions)

        subjects = {}
        for cs in ctx['class_sessions']:
            subjects.setdefault(cs.subject_id, cs.subject)
        ctx['subjects'] = sorted(subjects.values(), key=lambda s: s.code)
        ctx['assigned_periods'] = sum(cs.periods_per_week for cs in ctx['class_sessions'])

        avail = TeacherAvailability.objects.filter(teacher=teacher)
        ctx['availability_total'] = avail.count()
        ctx['availability_open'] = avail.filter(is_available=True).count()
        ctx['availability_blocked'] = avail.filter(is_available=False).count()
        return ctx


class TeacherCreateView(AcademicsAdminCRUDMixin, CreateView):
    model = TeacherProfile
    form_class = TeacherCreationForm
    template_name = 'academics/teacher_form.html'
    success_url = reverse_lazy('academics:teacher_list')

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, "Teacher account and profile created successfully.")
        return redirect(self.get_success_url())

class TeacherUpdateView(AcademicsAdminCRUDMixin, UpdateView):
    model = TeacherProfile
    form_class = TeacherProfileForm
    template_name = 'academics/teacher_form.html'
    success_url = reverse_lazy('academics:teacher_list')
    def form_valid(self, form):
        messages.success(self.request, "Teacher updated successfully.")
        return super().form_valid(form)

class TeacherDeleteView(ProtectedDeleteMixin, AcademicsAdminCRUDMixin, DeleteView):
    model = TeacherProfile
    template_name = 'academics/teacher_confirm_delete.html'
    success_url = reverse_lazy('academics:teacher_list')
    success_message = "Teacher deleted successfully."

    def perform_delete(self, obj):
        # Deleting the login account cascades to TeacherProfile (OneToOne CASCADE)
        # and TeacherAvailability. Class sessions / timetable slots SET_NULL the
        # teacher FK, so history is preserved without blocking the delete.
        obj.user.delete()


# -- ClassRepProfile --
class ClassRepListView(AcademicsAdminCRUDMixin, ListView):
    model = ClassRepProfile
    template_name = 'academics/class_rep_list.html'

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            'user', 'course_level', 'course_level__course', 'course_level__course__department',
        )
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
                | Q(user__username__icontains=q)
                | Q(course_level__course__name__icontains=q)
                | Q(course_level__course__code__icontains=q)
            )
        return qs


class ClassRepCreateView(AcademicsAdminCRUDMixin, CreateView):
    model = ClassRepProfile
    form_class = ClassRepCreationForm
    template_name = 'academics/class_rep_form.html'
    success_url = reverse_lazy('academics:class_rep_list')

    def form_valid(self, form):
        self.object = form.save()
        messages.success(
            self.request,
            (
                f"Class representative '{self.object.user.get_username()}' "
                f"created for course level {self.object.course_level}."
            ),
        )
        return redirect(self.get_success_url())


class ClassRepUpdateView(AcademicsAdminCRUDMixin, UpdateView):
    model = ClassRepProfile
    form_class = ClassRepProfileForm
    template_name = 'academics/class_rep_form.html'
    success_url = reverse_lazy('academics:class_rep_list')

    def form_valid(self, form):
        messages.success(self.request, "Class representative updated successfully.")
        return super().form_valid(form)


class ClassRepDeleteView(ProtectedDeleteMixin, AcademicsAdminCRUDMixin, DeleteView):
    model = ClassRepProfile
    template_name = 'academics/class_rep_confirm_delete.html'
    success_url = reverse_lazy('academics:class_rep_list')
    success_message = "Class representative deleted successfully."

    def perform_delete(self, obj):
        obj.user.delete()


# -- ClassSession --
class ClassSessionListView(AcademicsAdminCRUDMixin, ListView):
    model = ClassSession
    template_name = 'academics/class_session_list.html'

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            'subject', 'teacher', 'teacher__user', 'session',
            'course_level', 'course_level__course',
        )
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(subject__name__icontains=q)
                | Q(subject__code__icontains=q)
                | Q(course_level__course__name__icontains=q)
                | Q(course_level__course__code__icontains=q)
                | Q(teacher__user__first_name__icontains=q)
            )
        return qs

class ClassSessionCreateView(AcademicsAdminCRUDMixin, CreateView):
    model = ClassSession
    form_class = ClassSessionForm
    template_name = 'academics/class_session_form.html'
    success_url = reverse_lazy('academics:class_session_list')
    def form_valid(self, form):
        messages.success(self.request, "Class Session created successfully.")
        return super().form_valid(form)

class ClassSessionUpdateView(AcademicsAdminCRUDMixin, UpdateView):
    model = ClassSession
    form_class = ClassSessionForm
    template_name = 'academics/class_session_form.html'
    success_url = reverse_lazy('academics:class_session_list')
    def form_valid(self, form):
        messages.success(self.request, "Class Session updated successfully.")
        return super().form_valid(form)

class ClassSessionDeleteView(ProtectedDeleteMixin, AcademicsAdminCRUDMixin, DeleteView):
    model = ClassSession
    template_name = 'academics/class_session_confirm_delete.html'
    success_url = reverse_lazy('academics:class_session_list')
    success_message = "Class Session deleted successfully."

# -- Teacher Portal --
from django.forms import inlineformset_factory
from django.views.generic import TemplateView

TeacherAvailabilityFormSet = inlineformset_factory(
    TeacherProfile, TeacherAvailability,
    fields=['timeslot', 'is_available'],
    extra=0,
    can_delete=False,
)

class TeacherPortalView(RoleRequiredMixin, TemplateView):
    allowed_roles = ['TEACHER']
    template_name = 'academics/teacher_portal.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        teacher = getattr(self.request.user, 'teacher_profile', None)
        context['teacher'] = teacher
        
        if teacher:
            if self.request.POST:
                context['formset'] = TeacherAvailabilityFormSet(self.request.POST, instance=teacher)
            else:
                # Ensure all active timeslots have an availability record
                from scheduling.models import TimeSlot
                active_slots = TimeSlot.objects.filter(is_active=True)
                for slot in active_slots:
                    TeacherAvailability.objects.get_or_create(teacher=teacher, timeslot=slot, defaults={'is_available': True})
                
                context['formset'] = TeacherAvailabilityFormSet(instance=teacher)
        return context

    def post(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        teacher = context.get('teacher')
        formset = context.get('formset')
        
        if teacher and formset and formset.is_valid():
            formset.save()
            messages.success(request, "Availability updated successfully.")
            return redirect('academics:teacher_portal')
            
        return self.render_to_response(context)
