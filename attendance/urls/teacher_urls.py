# attendance/urls/teacher_urls.py
from django.urls import path
from attendance.views import (
    my_attendance,
    set_class_schedule, attendance_settings_view, override_attendance,
)

urlpatterns = [
    path('my/',                                    my_attendance,              name='my_attendance'),
    path('schedule/<int:classroom_id>/set/',       set_class_schedule,         name='set_class_schedule'),
    path('settings/<int:classroom_id>/',           attendance_settings_view,   name='attendance_settings'),
    path('override/<int:record_id>/',              override_attendance,        name='override_attendance'),
]
