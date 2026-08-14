# attendance/urls/report_urls.py
from django.urls import path
from attendance.views import (
    classroom_attendance_overview, daily_report, student_report,
    export_excel, check_schedule_api, admin_face_photos, engagement_report_view,
)

urlpatterns = [
    path('classroom/<int:classroom_id>/',                        classroom_attendance_overview, name='classroom_attendance_overview'),
    path('classroom/<int:classroom_id>/daily/',                  daily_report,                  name='daily_report'),
    path('classroom/<int:classroom_id>/student/<int:student_id>/', student_report,              name='student_report'),
    path('classroom/<int:classroom_id>/export/excel/',           export_excel,                  name='export_excel'),
    path('api/check-schedule/<str:meeting_code>/',               check_schedule_api,            name='check_schedule_api'),
    path('admin/face-photos/',                                   admin_face_photos,             name='admin_face_photos'),
    path('engagement-report/<int:meeting_id>/',                  engagement_report_view,        name='engagement_report'),
]
