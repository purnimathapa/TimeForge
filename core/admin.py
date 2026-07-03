from django.contrib import admin
from .models import Department, Room, Semester

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    search_fields = ('name', 'code')
    list_filter = ('is_active',)

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'room_type', 'capacity', 'department', 'is_active')
    search_fields = ('name', 'code', 'building')
    list_filter = ('room_type', 'is_active', 'department')

@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'start_date', 'end_date', 'is_active')
    search_fields = ('name', 'code')
    list_filter = ('is_active',)
