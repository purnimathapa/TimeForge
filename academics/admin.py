from django.contrib import admin
from .models import Subject, Section, TeacherProfile, TeacherAvailability

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'department', 'credit_hours', 'is_active')
    search_fields = ('code', 'name')
    list_filter = ('department', 'is_active')

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'year', 'section_label', 'department', 'semester', 'is_active')
    search_fields = ('name', 'section_label')
    list_filter = ('department', 'semester', 'year', 'is_active')

class TeacherAvailabilityInline(admin.TabularInline):
    model = TeacherAvailability
    extra = 1

@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'employee_id', 'title', 'department', 'is_active')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'employee_id')
    list_filter = ('department', 'is_active')
    inlines = [TeacherAvailabilityInline]

@admin.register(TeacherAvailability)
class TeacherAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'day_of_week', 'start_time', 'end_time', 'is_available')
    list_filter = ('day_of_week', 'is_available')
