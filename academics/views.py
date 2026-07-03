from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db.models import Q
from django.contrib import messages
from accounts.mixins import RoleRequiredMixin
from .models import Subject, Section, TeacherProfile, ClassSession
from scheduling.models import TeacherAvailability
from .forms import SubjectForm, SectionForm, TeacherProfileForm, ClassSessionForm

class AcademicsAdminCRUDMixin(RoleRequiredMixin):
    allowed_roles = ['ADMIN']
    paginate_by = 20

# -- Subject --
class SubjectListView(AcademicsAdminCRUDMixin, ListView):
    model = Subject
    def get_queryset(self):
        qs = super().get_queryset()
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

class SubjectDeleteView(AcademicsAdminCRUDMixin, DeleteView):
    model = Subject
    success_url = reverse_lazy('academics:subject_list')
    def delete(self, request, *args, **kwargs):
        messages.success(request, "Subject deleted successfully.")
        return super().delete(request, *args, **kwargs)

# -- Section --
class SectionListView(AcademicsAdminCRUDMixin, ListView):
    model = Section
    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(section_label__icontains=q))
        return qs

class SectionCreateView(AcademicsAdminCRUDMixin, CreateView):
    model = Section
    form_class = SectionForm
    success_url = reverse_lazy('academics:section_list')
    def form_valid(self, form):
        messages.success(self.request, "Section created successfully.")
        return super().form_valid(form)

class SectionUpdateView(AcademicsAdminCRUDMixin, UpdateView):
    model = Section
    form_class = SectionForm
    success_url = reverse_lazy('academics:section_list')
    def form_valid(self, form):
        messages.success(self.request, "Section updated successfully.")
        return super().form_valid(form)

class SectionDeleteView(AcademicsAdminCRUDMixin, DeleteView):
    model = Section
    success_url = reverse_lazy('academics:section_list')
    def delete(self, request, *args, **kwargs):
        messages.success(request, "Section deleted successfully.")
        return super().delete(request, *args, **kwargs)

# -- TeacherProfile --
class TeacherListView(AcademicsAdminCRUDMixin, ListView):
    model = TeacherProfile
    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(employee_id__icontains=q))
        return qs

class TeacherCreateView(AcademicsAdminCRUDMixin, CreateView):
    model = TeacherProfile
    form_class = TeacherProfileForm
    success_url = reverse_lazy('academics:teacher_list')
    def form_valid(self, form):
        messages.success(self.request, "Teacher created successfully.")
        return super().form_valid(form)

class TeacherUpdateView(AcademicsAdminCRUDMixin, UpdateView):
    model = TeacherProfile
    form_class = TeacherProfileForm
    success_url = reverse_lazy('academics:teacher_list')
    def form_valid(self, form):
        messages.success(self.request, "Teacher updated successfully.")
        return super().form_valid(form)

class TeacherDeleteView(AcademicsAdminCRUDMixin, DeleteView):
    model = TeacherProfile
    success_url = reverse_lazy('academics:teacher_list')
    def delete(self, request, *args, **kwargs):
        messages.success(request, "Teacher deleted successfully.")
        return super().delete(request, *args, **kwargs)

# -- ClassSession --
class ClassSessionListView(AcademicsAdminCRUDMixin, ListView):
    model = ClassSession
    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(subject__name__icontains=q) | Q(section__name__icontains=q) | Q(teacher__user__first_name__icontains=q))
        return qs

class ClassSessionCreateView(AcademicsAdminCRUDMixin, CreateView):
    model = ClassSession
    form_class = ClassSessionForm
    success_url = reverse_lazy('academics:class_session_list')
    def form_valid(self, form):
        messages.success(self.request, "Class Session created successfully.")
        return super().form_valid(form)

class ClassSessionUpdateView(AcademicsAdminCRUDMixin, UpdateView):
    model = ClassSession
    form_class = ClassSessionForm
    success_url = reverse_lazy('academics:class_session_list')
    def form_valid(self, form):
        messages.success(self.request, "Class Session updated successfully.")
        return super().form_valid(form)

class ClassSessionDeleteView(AcademicsAdminCRUDMixin, DeleteView):
    model = ClassSession
    success_url = reverse_lazy('academics:class_session_list')
    def delete(self, request, *args, **kwargs):
        messages.success(request, "Class Session deleted successfully.")
        return super().delete(request, *args, **kwargs)

# -- Teacher Portal --
from django.forms import inlineformset_factory
from django.shortcuts import redirect
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
        teacher = getattr(self.request.user, 'teacherprofile', None)
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

