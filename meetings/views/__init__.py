# meetings/views/__init__.py
# Re-exports all view functions for backwards compatibility with urls.py
from .classroom_views import (
    create_classroom,
    teacher_classrooms,
    classroom_detail,
    join_classroom_request,
    student_classrooms,
    approve_join_request,
    approve_all_join_requests,
    deny_join_request,
    deny_all_join_requests,
    toggle_auto_approve,
    remove_student,
    delete_classroom,
    leave_classroom,
    start_classroom_meeting,
    api_classrooms,
)
from .meeting_views import (
    generate_meeting_code,
    create_meeting,
    teacher_meetings,
    student_meetings,
    join_meeting,
    pre_join,
    verify_face_prejoin,
    livekit_token,
    meeting_attendance,
    meeting_summary,
    end_meeting,
    continue_meeting,
    leave_meeting,
    get_participants,
    delete_meeting,
    cancel_meeting,
)
from .meeting_controls import (
    sleep_meeting,
    unfreeze_meeting,
    get_meeting_status,
    kick_participant,
    revoke_ban,
    get_banned_users,
    meeting_global_control,
)
from .attendance_history_views import (
    classroom_attendance_history,
    classroom_attendance_detail,
)
from .material_views import (
    classroom_materials_view,
    upload_study_material,
    create_material_unit,
    delete_study_material,
    toggle_material_bookmark,
    download_study_material,
    material_detail_api,
    digital_library_view,
)
from .recording_views import (
    meeting_chunked_upload,
)
from .quiz_live_views import (
    get_available_classroom_quizzes,
    start_meeting_quiz,
    submit_meeting_quiz,
    get_meeting_quiz_submissions,
)


