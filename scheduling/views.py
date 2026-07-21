from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db.models import Q
from django.contrib import messages
from accounts.mixins import RoleRequiredMixin
from core.mixins import SchoolFormMixin, ProtectedDeleteMixin
from core.tenant import filter_by_school
from .models import TimeSlot, Constraint
from .forms import TimeSlotForm, ConstraintForm

class SchedulingAdminCRUDMixin(SchoolFormMixin, RoleRequiredMixin):
    allowed_roles = ['ADMIN']
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        if self.model is Constraint:
            qs = filter_by_school(qs, self.request, 'semester__school')
        return qs

# -- TimeSlot (institution-wide calendar grid; not school-scoped) --
class TimeSlotListView(SchedulingAdminCRUDMixin, ListView):
    model = TimeSlot
    def get_queryset(self):
        return super().get_queryset()

class TimeSlotCreateView(SchedulingAdminCRUDMixin, CreateView):
    model = TimeSlot
    form_class = TimeSlotForm
    success_url = reverse_lazy('scheduling:timeslot_list')
    def form_valid(self, form):
        messages.success(self.request, "Time Slot created successfully.")
        return super().form_valid(form)

class TimeSlotUpdateView(SchedulingAdminCRUDMixin, UpdateView):
    model = TimeSlot
    form_class = TimeSlotForm
    success_url = reverse_lazy('scheduling:timeslot_list')
    def form_valid(self, form):
        messages.success(self.request, "Time Slot updated successfully.")
        return super().form_valid(form)

class TimeSlotDeleteView(ProtectedDeleteMixin, SchedulingAdminCRUDMixin, DeleteView):
    model = TimeSlot
    success_url = reverse_lazy('scheduling:timeslot_list')
    success_message = "Time Slot deleted successfully."

# -- Constraint --
class ConstraintListView(SchedulingAdminCRUDMixin, ListView):
    model = Constraint
    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(constraint_type__icontains=q))
        return qs

class ConstraintCreateView(SchedulingAdminCRUDMixin, CreateView):
    model = Constraint
    form_class = ConstraintForm
    success_url = reverse_lazy('scheduling:constraint_list')
    def form_valid(self, form):
        messages.success(self.request, "Constraint created successfully.")
        return super().form_valid(form)
        
    def form_invalid(self, form):
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, f"{field}: {error}")
        return super().form_invalid(form)

class ConstraintUpdateView(SchedulingAdminCRUDMixin, UpdateView):
    model = Constraint
    form_class = ConstraintForm
    success_url = reverse_lazy('scheduling:constraint_list')
    def form_valid(self, form):
        messages.success(self.request, "Constraint updated successfully.")
        return super().form_valid(form)

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, f"{field}: {error}")
        return super().form_invalid(form)

class ConstraintDeleteView(ProtectedDeleteMixin, SchedulingAdminCRUDMixin, DeleteView):
    model = Constraint
    success_url = reverse_lazy('scheduling:constraint_list')
    success_message = "Constraint deleted successfully."
