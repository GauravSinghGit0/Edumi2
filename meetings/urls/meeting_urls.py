# meetings/urls/meeting_urls.py
from django.urls import path
from meetings.views import (
    create_meeting, teacher_meetings, student_meetings, join_meeting,
    pre_join, verify_face_prejoin, livekit_token, meeting_attendance,
    meeting_summary, end_meeting, continue_meeting, leave_meeting, get_participants,
    delete_meeting, cancel_meeting, meeting_chunked_upload,
    get_available_classroom_quizzes, start_meeting_quiz, submit_meeting_quiz,
    get_meeting_quiz_submissions,
)

urlpatterns = [
    path('create/',                                  create_meeting,                  name='create_meeting'),
    path('teacher/',                                 teacher_meetings,                name='teacher_meetings'),
    path('student/',                                 student_meetings,                name='student_meetings'),
    path('join/<str:meeting_code>/',                 join_meeting,                    name='join_meeting'),
    path('token/<str:meeting_code>/',                livekit_token,                   name='livekit_token'),
    path('end/<int:meeting_id>/',                    end_meeting,                     name='end_meeting'),
    path('continue/<int:meeting_id>/',               continue_meeting,                name='continue_meeting'),
    path('leave/<int:meeting_id>/',                  leave_meeting,                   name='leave_meeting'),
    path('participants/<int:meeting_id>/',           get_participants,                 name='get_participants'),
    path('delete/<int:meeting_id>/',                 delete_meeting,                  name='delete_meeting'),
    path('cancel/<int:meeting_id>/',                 cancel_meeting,                  name='cancel_meeting'),
    path('attendance/<str:meeting_code>/',           meeting_attendance,              name='meeting_attendance'),
    path('summary/<str:meeting_code>/',              meeting_summary,                 name='meeting_summary'),
    path('prep/<str:meeting_code>/',                 pre_join,                        name='pre_join'),
    path('verify-prejoin/',                          verify_face_prejoin,             name='verify_face_prejoin'),
    path('recording/upload/',                        meeting_chunked_upload,          name='meeting_chunked_upload'),
    path('available-quizzes/<str:meeting_code>/',    get_available_classroom_quizzes, name='get_available_classroom_quizzes'),
    path('start-quiz/<str:meeting_code>/',           start_meeting_quiz,              name='start_meeting_quiz'),
    path('submit-quiz/<str:meeting_code>/',          submit_meeting_quiz,             name='submit_meeting_quiz'),
    path('quiz-submissions/<int:meeting_id>/<int:quiz_id>/', get_meeting_quiz_submissions, name='get_meeting_quiz_submissions'),
]

