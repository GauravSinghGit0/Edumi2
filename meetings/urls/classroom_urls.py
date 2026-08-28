# meetings/urls/classroom_urls.py
from django.urls import path
from meetings.views import (
    create_classroom, teacher_classrooms, student_classrooms, classroom_detail,
    join_classroom_request, approve_join_request, approve_all_join_requests,
    deny_join_request, deny_all_join_requests, toggle_auto_approve,
    remove_student, delete_classroom, leave_classroom, start_classroom_meeting,
    classroom_attendance_history, classroom_attendance_detail, api_classrooms,
    classroom_materials_view, upload_study_material, create_material_unit,
    delete_study_material, toggle_material_bookmark, download_study_material,
    material_detail_api, digital_library_view,
)

urlpatterns = [
    path('api/classrooms/',                                      api_classrooms,                name='api_classrooms'),
    path('classroom/create/',                                    create_classroom,              name='create_classroom'),
    path('classroom/teacher/',                                   teacher_classrooms,            name='teacher_classrooms'),
    path('classroom/student/',                                   student_classrooms,            name='student_classrooms'),
    path('classroom/<int:classroom_id>/',                        classroom_detail,              name='classroom_detail'),
    path('classroom/join/',                                      join_classroom_request,        name='join_classroom_request'),
    path('classroom/approve/<int:membership_id>/',               approve_join_request,          name='approve_join_request'),
    path('classroom/<int:classroom_id>/approve-all/',           approve_all_join_requests,     name='approve_all_join_requests'),
    path('classroom/deny/<int:membership_id>/',                  deny_join_request,             name='deny_join_request'),
    path('classroom/<int:classroom_id>/deny-all/',              deny_all_join_requests,        name='deny_all_join_requests'),
    path('classroom/<int:classroom_id>/toggle-auto-approve/',   toggle_auto_approve,           name='toggle_auto_approve'),
    path('classroom/remove/<int:membership_id>/',                remove_student,                name='remove_student'),
    path('classroom/<int:classroom_id>/delete/',                 delete_classroom,              name='delete_classroom'),
    path('classroom/<int:classroom_id>/leave/',                  leave_classroom,               name='leave_classroom'),
    path('classroom/<int:classroom_id>/start-meeting/',          start_classroom_meeting,       name='start_classroom_meeting'),
    path('classroom/attendance/history/',                        classroom_attendance_history,  name='classroom_attendance_history'),
    path('classroom/<int:classroom_id>/attendance/',             classroom_attendance_detail,   name='classroom_attendance_detail'),

    # Study Materials & Digital Library
    path('classroom/<int:classroom_id>/materials/',              classroom_materials_view,      name='classroom_materials'),
    path('classroom/<int:classroom_id>/materials/upload/',       upload_study_material,         name='upload_study_material'),
    path('classroom/<int:classroom_id>/units/create/',           create_material_unit,          name='create_material_unit'),
    path('materials/<int:material_id>/delete/',                  delete_study_material,         name='delete_study_material'),
    path('materials/<int:material_id>/bookmark/',                toggle_material_bookmark,      name='toggle_material_bookmark'),
    path('materials/<int:material_id>/download/',                download_study_material,       name='download_study_material'),
    path('materials/<int:material_id>/detail-api/',              material_detail_api,           name='material_detail_api'),
    path('library/',                                             digital_library_view,          name='digital_library'),
]

