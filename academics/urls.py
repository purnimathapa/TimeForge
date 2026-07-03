from django.urls import path
from . import views

app_name = 'academics'

urlpatterns = [
    path('subjects/', views.SubjectListView.as_view(), name='subject_list'),
    path('subjects/create/', views.SubjectCreateView.as_view(), name='subject_create'),
    path('subjects/<int:pk>/edit/', views.SubjectUpdateView.as_view(), name='subject_update'),
    path('subjects/<int:pk>/delete/', views.SubjectDeleteView.as_view(), name='subject_delete'),

    path('sections/', views.SectionListView.as_view(), name='section_list'),
    path('sections/create/', views.SectionCreateView.as_view(), name='section_create'),
    path('sections/<int:pk>/edit/', views.SectionUpdateView.as_view(), name='section_update'),
    path('sections/<int:pk>/delete/', views.SectionDeleteView.as_view(), name='section_delete'),

    path('teachers/', views.TeacherListView.as_view(), name='teacher_list'),
    path('teachers/create/', views.TeacherCreateView.as_view(), name='teacher_create'),
    path('teachers/<int:pk>/edit/', views.TeacherUpdateView.as_view(), name='teacher_update'),
    path('teachers/<int:pk>/delete/', views.TeacherDeleteView.as_view(), name='teacher_delete'),

    path('class-sessions/', views.ClassSessionListView.as_view(), name='class_session_list'),
    path('class-sessions/create/', views.ClassSessionCreateView.as_view(), name='class_session_create'),
    path('class-sessions/<int:pk>/edit/', views.ClassSessionUpdateView.as_view(), name='class_session_update'),
    path('class-sessions/<int:pk>/delete/', views.ClassSessionDeleteView.as_view(), name='class_session_delete'),

    # Teacher Portal
    path('portal/', views.TeacherPortalView.as_view(), name='teacher_portal'),
]
