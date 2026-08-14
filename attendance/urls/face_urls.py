# attendance/urls/face_urls.py
from django.urls import path
from attendance.views import (
    face_setup, upload_face_photo, capture_face_photo,
    detect_face, face_registration_status, update_profile_info,
)

urlpatterns = [
    path('face/setup/',           face_setup,               name='face_setup'),
    path('face/upload/',          upload_face_photo,         name='upload_face_photo'),
    path('face/capture/',         capture_face_photo,        name='capture_face_photo'),
    path('face/detect/',          detect_face,               name='detect_face'),
    path('face/status/',          face_registration_status,  name='face_status'),
    path('face/update-profile/',  update_profile_info,       name='update_profile_info'),
]
