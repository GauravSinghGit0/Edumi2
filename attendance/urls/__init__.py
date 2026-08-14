# attendance/urls/__init__.py
# This is the file Django loads for include('attendance.urls')
#
# Sub-files:
#   face_urls.py    — face setup, upload, camera capture, detect, status, update profile
#   teacher_urls.py — my_attendance, class schedule, attendance settings, override
#   report_urls.py  — classroom/daily/student reports, Excel export, schedule API, engagement

from django.urls import path, include

urlpatterns = [
    path('', include('attendance.urls.face_urls')),
    path('', include('attendance.urls.teacher_urls')),
    path('', include('attendance.urls.report_urls')),
]
