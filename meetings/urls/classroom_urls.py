# meetings/urls/classroom_urls.py
from django.urls import path
from meetings.views import (
    create_classroom, teacher_classrooms, student_classrooms, classroom_detail,
    join_classroom_request, approve_join_request, deny_join_request,
    remove_student, delete_classroom, leave_classroom, start_classroom_meeting,
    classroom_attendance_history, classroom_attendance_detail, api_classrooms,
)

urlpatterns = [
    path('api/classrooms/',                              api_classrooms,                name='api_classrooms'),
    path('classroom/create/',                            create_classroom,              name='create_classroom'),
    path('classroom/teacher/',                           teacher_classrooms,            name='teacher_classrooms'),
    path('classroom/student/',                           student_classrooms,            name='student_classrooms'),
    path('classroom/<int:classroom_id>/',                classroom_detail,              name='classroom_detail'),
    path('classroom/join/',                              join_classroom_request,        name='join_classroom_request'),
    path('classroom/approve/<int:membership_id>/',       approve_join_request,          name='approve_join_request'),
    path('classroom/deny/<int:membership_id>/',          deny_join_request,             name='deny_join_request'),
    path('classroom/remove/<int:membership_id>/',        remove_student,                name='remove_student'),
    path('classroom/<int:classroom_id>/delete/',         delete_classroom,              name='delete_classroom'),
    path('classroom/<int:classroom_id>/leave/',          leave_classroom,               name='leave_classroom'),
    path('classroom/<int:classroom_id>/start-meeting/',  start_classroom_meeting,       name='start_classroom_meeting'),
    path('classroom/attendance/history/',                classroom_attendance_history,  name='classroom_attendance_history'),
    path('classroom/<int:classroom_id>/attendance/',     classroom_attendance_detail,   name='classroom_attendance_detail'),
]
