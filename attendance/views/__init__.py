# attendance/views/__init__.py
from .face_registration_views import (
    face_setup, upload_face_photo, capture_face_photo,
    detect_face, update_profile_info, face_registration_status,
)
from .teacher_views import (
    my_attendance,
    set_class_schedule, attendance_settings_view, override_attendance,
)
from .report_views import (
    daily_report, student_report, classroom_attendance_overview,
    export_excel, check_schedule_api, engagement_report_view, admin_face_photos,
)
