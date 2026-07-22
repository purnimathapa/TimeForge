from django.urls import path
from django.views.generic import RedirectView
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', views.custom_logout, name='logout'),

    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='accounts/password_reset_form.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'), name='password_reset_complete'),

    path(
        'teacher/create/',
        RedirectView.as_view(pattern_name='academics:teacher_create', permanent=False),
        name='teacher_create',
    ),
    path('admin/create/', views.AdminCreateView.as_view(), name='admin_create'),
    path(
        'class-rep/create/',
        RedirectView.as_view(pattern_name='academics:class_rep_create', permanent=False),
        name='class_rep_create',
    ),
    path('profile/', views.ProfileView.as_view(), name='profile'),
]
