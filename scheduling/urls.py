from django.urls import path
from . import views

app_name = 'scheduling'

urlpatterns = [
    path('timeslots/', views.TimeSlotListView.as_view(), name='timeslot_list'),
    path('timeslots/create/', views.TimeSlotCreateView.as_view(), name='timeslot_create'),
    path('timeslots/<int:pk>/edit/', views.TimeSlotUpdateView.as_view(), name='timeslot_update'),
    path('timeslots/<int:pk>/delete/', views.TimeSlotDeleteView.as_view(), name='timeslot_delete'),

    path('constraints/', views.ConstraintListView.as_view(), name='constraint_list'),
    path('constraints/create/', views.ConstraintCreateView.as_view(), name='constraint_create'),
    path('constraints/<int:pk>/edit/', views.ConstraintUpdateView.as_view(), name='constraint_update'),
    path('constraints/<int:pk>/delete/', views.ConstraintDeleteView.as_view(), name='constraint_delete'),
]
