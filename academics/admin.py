from django.contrib import admin
from .models import (
    Subject, Course, CourseLevel, CourseLevelOffering,
    TeacherProfile, ClassRepProfile, ClassSession,
)
from scheduling.models import TeacherAvailability


class CourseLevelInline(admin.TabularInline):
    model = CourseLevel
    extra = 0
    fields = ('level', 'student_count', 'is_active')
    ordering = ('level',)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'department', 'is_active')
    search_fields = ('code', 'name')
    list_filter = ('department', 'is_active')
    inlines = [CourseLevelInline]


@admin.register(CourseLevel)
class CourseLevelAdmin(admin.ModelAdmin):
    list_display = ('course', 'level', 'student_count', 'is_active')
    search_fields = ('course__code', 'course__name')
    list_filter = ('level', 'is_active', 'course__department')


@admin.register(CourseLevelOffering)
class CourseLevelOfferingAdmin(admin.ModelAdmin):
    list_display = ('course_level', 'session', 'shift')
    list_filter = ('shift', 'session', 'course_level__level')
    search_fields = ('course_level__course__code', 'course_level__course__name')


@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = ('subject', 'course_level', 'session', 'teacher', 'periods_per_week')
    list_filter = ('subject', 'course_level__course', 'session', 'teacher')
    search_fields = ('subject__code', 'subject__name', 'course_level__course__code')


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'department_names', 'credit_hours', 'is_active')
    search_fields = ('code', 'name')
    list_filter = ('departments', 'is_active')
    filter_horizontal = ('departments',)


class TeacherAvailabilityInline(admin.TabularInline):
    model = TeacherAvailability
    extra = 1


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'employee_id', 'title', 'department_names', 'is_active')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'employee_id')
    list_filter = ('departments', 'is_active')
    filter_horizontal = ('departments',)
    inlines = [TeacherAvailabilityInline]


@admin.register(ClassRepProfile)
class ClassRepProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'course_level', 'is_active')
    search_fields = (
        'user__username',
        'user__first_name',
        'user__last_name',
        'course_level__course__name',
        'course_level__course__code',
    )
    list_filter = ('is_active', 'course_level__level', 'course_level__course')
