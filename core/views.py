from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db.models import Q
from django.contrib import messages
from accounts.mixins import RoleRequiredMixin
from core.mixins import SchoolFormMixin, SchoolScopedMixin, ProtectedDeleteMixin
from .models import Department, Room, Session
from .forms import DepartmentForm, RoomForm, SessionForm
from django.shortcuts import redirect
from django.views.generic import TemplateView

class HomeView(TemplateView):
    template_name = 'core/home.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard:dashboard')
        return super().get(request, *args, **kwargs)

# Optional Mixin for common CRUD patterns
class CoreAdminCRUDMixin(SchoolScopedMixin, SchoolFormMixin, RoleRequiredMixin):
    allowed_roles = ['ADMIN']
    paginate_by = 20

# -- Department --
class DepartmentListView(CoreAdminCRUDMixin, ListView):
    model = Department
    
    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        return qs

class DepartmentCreateView(CoreAdminCRUDMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    success_url = reverse_lazy('core:department_list')
    
    def form_valid(self, form):
        messages.success(self.request, "Department created successfully.")
        return super().form_valid(form)

class DepartmentUpdateView(CoreAdminCRUDMixin, UpdateView):
    model = Department
    form_class = DepartmentForm
    success_url = reverse_lazy('core:department_list')
    
    def form_valid(self, form):
        messages.success(self.request, "Department updated successfully.")
        return super().form_valid(form)

class DepartmentDeleteView(ProtectedDeleteMixin, CoreAdminCRUDMixin, DeleteView):
    model = Department
    success_url = reverse_lazy('core:department_list')
    success_message = "Department deleted successfully."

# -- Room --
class RoomListView(CoreAdminCRUDMixin, ListView):
    model = Room
    
    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(building__icontains=q))
        return qs

class RoomCreateView(CoreAdminCRUDMixin, CreateView):
    model = Room
    form_class = RoomForm
    success_url = reverse_lazy('core:room_list')
    
    def form_valid(self, form):
        messages.success(self.request, "Room created successfully.")
        return super().form_valid(form)

class RoomUpdateView(CoreAdminCRUDMixin, UpdateView):
    model = Room
    form_class = RoomForm
    success_url = reverse_lazy('core:room_list')
    
    def form_valid(self, form):
        messages.success(self.request, "Room updated successfully.")
        return super().form_valid(form)

class RoomDeleteView(ProtectedDeleteMixin, CoreAdminCRUDMixin, DeleteView):
    model = Room
    success_url = reverse_lazy('core:room_list')
    success_message = "Room deleted successfully."

# -- Session --
class SessionListView(CoreAdminCRUDMixin, ListView):
    model = Session
    template_name = 'core/session_list.html'
    
    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(name__icontains=q))
        return qs

class SessionCreateView(CoreAdminCRUDMixin, CreateView):
    model = Session
    form_class = SessionForm
    template_name = 'core/session_form.html'
    success_url = reverse_lazy('core:session_list')
    
    def form_valid(self, form):
        messages.success(self.request, "Session created successfully.")
        return super().form_valid(form)

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, f"{field}: {error}")
        return super().form_invalid(form)

class SessionUpdateView(CoreAdminCRUDMixin, UpdateView):
    model = Session
    form_class = SessionForm
    template_name = 'core/session_form.html'
    success_url = reverse_lazy('core:session_list')
    
    def form_valid(self, form):
        messages.success(self.request, "Session updated successfully.")
        return super().form_valid(form)

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, f"{field}: {error}")
        return super().form_invalid(form)

class SessionDeleteView(ProtectedDeleteMixin, CoreAdminCRUDMixin, DeleteView):
    model = Session
    template_name = 'core/session_confirm_delete.html'
    success_url = reverse_lazy('core:session_list')
    success_message = "Session deleted successfully."
