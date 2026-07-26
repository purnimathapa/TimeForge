from django.urls import path
from . import views

app_name = 'academics'

urlpatterns = [
    path('subjects/', views.SubjectListView.as_view(), name='subject_list'),
    path('subjects/create/', views.SubjectCreateView.as_view(), name='subject_create'),
    path('subjects/<int:pk>/edit/', views.SubjectUpdateView.as_view(), name='subject_update'),
    path('subjects/<int:pk>/delete/', views.SubjectDeleteView.as_view(), name='subject_delete'),

    path('courses/', views.CourseListView.as_view(), name='course_list'),
    path('courses/create/', views.CourseCreateView.as_view(), name='course_create'),
    path('courses/<int:pk>/', views.CourseDetailView.as_view(), name='course_detail'),
    path(
        'courses/<int:pk>/running-semesters/add/',
        views.RunningSemesterCreateView.as_view(),
        name='running_semester_create',
    ),
    path(
        'offerings/<int:pk>/shift/',
        views.OfferingShiftUpdateView.as_view(),
        name='offering_shift_update',
    ),
    path('courses/<int:pk>/edit/', views.CourseUpdateView.as_view(), name='course_update'),
    path('courses/<int:pk>/delete/', views.CourseDeleteView.as_view(), name='course_delete'),

    path('teachers/', views.TeacherListView.as_view(), name='teacher_list'),
    path('teachers/create/', views.TeacherCreateView.as_view(), name='teacher_create'),
    path('teachers/<int:pk>/', views.TeacherDetailView.as_view(), name='teacher_detail'),
    path('teachers/<int:pk>/edit/', views.TeacherUpdateView.as_view(), name='teacher_update'),
    path('teachers/<int:pk>/delete/', views.TeacherDeleteView.as_view(), name='teacher_delete'),

    path('class-reps/', views.ClassRepListView.as_view(), name='class_rep_list'),
    path('class-reps/create/', views.ClassRepCreateView.as_view(), name='class_rep_create'),
    path('class-reps/<int:pk>/edit/', views.ClassRepUpdateView.as_view(), name='class_rep_update'),
    path('class-reps/<int:pk>/delete/', views.ClassRepDeleteView.as_view(), name='class_rep_delete'),

    path('class-sessions/', views.ClassSessionListView.as_view(), name='class_session_list'),
    path('class-sessions/create/', views.ClassSessionCreateView.as_view(), name='class_session_create'),
    path('class-sessions/<int:pk>/edit/', views.ClassSessionUpdateView.as_view(), name='class_session_update'),
    path('class-sessions/<int:pk>/delete/', views.ClassSessionDeleteView.as_view(), name='class_session_delete'),

    # Teacher Portal
    path('portal/', views.TeacherPortalView.as_view(), name='teacher_portal'),
]
