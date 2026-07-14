from django.contrib import admin
from .models import Department, Room, School, Semester


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at')
    search_fields = ('name', 'code')
    list_filter = ('is_active',)
    prepopulated_fields = {'code': ('name',)}


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'school', 'is_active')
    search_fields = ('name', 'code')
    list_filter = ('is_active', 'school')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'room_type', 'capacity', 'school', 'department', 'is_active')
    search_fields = ('name', 'code', 'building')
    list_filter = ('room_type', 'is_active', 'school', 'department')


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'school', 'start_date', 'end_date', 'is_active')
    search_fields = ('name', 'code')
    list_filter = ('is_active', 'school')
