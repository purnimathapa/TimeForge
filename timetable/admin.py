from django.contrib import admin
from .models import Timetable, TimetableSlot


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display  = ('session', 'version', 'status', 'penalty_score', 'slot_count', 'generated_at')
    list_filter   = ('status', 'session')
    readonly_fields = ('version', 'generated_at', 'penalty_score')
    ordering      = ('-generated_at',)


@admin.register(TimetableSlot)
class TimetableSlotAdmin(admin.ModelAdmin):
    list_display  = ('timetable', 'class_session', 'timeslot', 'room', 'teacher', 'is_locked', 'is_manual')
    list_filter   = ('timetable__session', 'is_locked', 'is_manual')
    list_select_related = ('timetable', 'class_session', 'timeslot', 'room', 'teacher')
    search_fields = (
        'class_session__subject__name',
        'class_session__course_level__course__name',
        'class_session__course_level__course__code',
        'room__name',
        'teacher__user__first_name',
        'teacher__user__last_name',
    )
