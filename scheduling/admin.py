from django.contrib import admin
from .models import TimeSlot, Constraint

@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ('day_of_week', 'period_number', 'start_time', 'end_time', 'is_active')
    list_filter = ('day_of_week', 'is_active')
    ordering = ('day_of_week', 'period_number')

@admin.register(Constraint)
class ConstraintAdmin(admin.ModelAdmin):
    list_display = ('name', 'constraint_type', 'target_type', 'is_hard', 'semester', 'is_active')
    list_filter = ('constraint_type', 'target_type', 'is_hard', 'is_active', 'semester')
    search_fields = ('name',)
