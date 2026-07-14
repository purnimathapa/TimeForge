from django.urls import path
from . import views

app_name = 'timetable'

urlpatterns = [
    path('generate/', views.GenerateTimetableView.as_view(), name='generate'),
    path('list/',     views.TimetableListView.as_view(),     name='list'),
    path('<int:pk>/publish/', views.PublishTimetableView.as_view(), name='publish_timetable'),
    path('<int:pk>/discard/', views.DiscardDraftTimetableView.as_view(), name='discard_timetable'),
    path('<int:pk>/', views.TimetableDetailView.as_view(),   name='detail'),

    path('my-routine/', views.MyRoutineView.as_view(), name='my_routine'),
    path('directory/', views.TimetableDirectoryView.as_view(), name='directory'),

    # ── Grid views (Prompt 12) ──
    path('teacher/',   views.TeacherTimetableView.as_view(),  name='teacher_view'),
    path('room/',      views.RoomTimetableView.as_view(),     name='room_view'),
    path('section/',   views.SectionTimetableView.as_view(),  name='section_view'),
    path('reports/',   views.ReportsView.as_view(),           name='reports'),
    path('export/<str:scope>/<str:file_format>/', views.ExportTimetableView.as_view(), name='export'),
    path('slots/move/', views.MoveSlotView.as_view(),          name='move_slot'),
    path('slots/unlock/', views.UnlockSlotView.as_view(),      name='unlock_slot'),
    path('slots/validate-batch/', views.ValidateBatchView.as_view(), name='validate_batch'),
    path('change-sets/publish/', views.PublishChangeSetView.as_view(), name='publish_change_set'),
    path('change-sets/discard/', views.DiscardChangeSetView.as_view(), name='discard_change_set'),
    path('conflicts/', views.ConflictReportView.as_view(),    name='conflict_report'),
]
