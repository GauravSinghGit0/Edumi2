"""
In-meeting host control views:
sleep/unfreeze, kick/ban, global mute/camera controls.
"""
import json

from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.contrib.auth import get_user_model
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from meetings.models import Meeting, KickedParticipant

User = get_user_model()


@login_required
def sleep_meeting(request, meeting_code):
    """Put a live meeting into sleep/pause mode."""
    meeting = get_object_or_404(Meeting, meeting_code=meeting_code)
    if request.user != meeting.teacher:
        return JsonResponse({'error': 'Only the meeting host can put it to sleep'}, status=403)
    if meeting.status != 'live':
        return JsonResponse({'error': 'Only live meetings can be put to sleep'}, status=400)
    meeting.put_to_sleep()
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'meeting_{meeting.meeting_code}',
        {'type': 'meeting_sleeping', 'message': 'Meeting has been put to sleep by the host'}
    )
    return JsonResponse({'status': 'success', 'message': 'Meeting is now sleeping', 'sleep_status': 'sleeping'})


@login_required
def unfreeze_meeting(request, meeting_code):
    """Wake up a sleeping meeting."""
    meeting = get_object_or_404(Meeting, meeting_code=meeting_code)
    if request.user != meeting.teacher:
        return JsonResponse({'error': 'Only the meeting host can unfreeze it'}, status=403)
    if meeting.sleep_status != 'sleeping':
        return JsonResponse({'error': 'Meeting is not in sleep mode'}, status=400)
    meeting.unfreeze()
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'meeting_{meeting.meeting_code}',
        {'type': 'meeting_unfrozen', 'message': 'Meeting is now active'}
    )
    return JsonResponse({'status': 'success', 'message': 'Meeting is now active', 'sleep_status': 'active'})


@login_required
def get_meeting_status(request, meeting_code):
    """Return current status and sleep status of a meeting."""
    meeting = get_object_or_404(Meeting, meeting_code=meeting_code)
    return JsonResponse({
        'status': meeting.status,
        'sleep_status': meeting.sleep_status,
        'can_join': meeting.can_join(),
        'is_teacher': request.user == meeting.teacher,
    })


@login_required
@require_http_methods(["POST"])
def kick_participant(request, meeting_id, user_id):
    """Teacher kicks a student from a meeting with a 1-hour ban."""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    if meeting.teacher != request.user and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'})
    user_to_kick = get_object_or_404(User, id=user_id)
    ban_until = timezone.now() + timezone.timedelta(hours=1)
    KickedParticipant.objects.update_or_create(
        meeting=meeting, user=user_to_kick, defaults={'banned_until': ban_until}
    )
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'meeting_{meeting.meeting_code}',
        {'type': 'kick_user', 'user_id': user_to_kick.id, 'message': 'You have been kicked by the teacher. You cannot rejoin for 1 hour.'}
    )
    return JsonResponse({'status': 'success', 'message': f'{user_to_kick.username} kicked successfully'})


@login_required
@require_http_methods(["POST"])
def revoke_ban(request, meeting_id, user_id):
    """Teacher lifts a kick-ban before the 1-hour limit expires."""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    if meeting.teacher != request.user and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'})
    KickedParticipant.objects.filter(meeting=meeting, user_id=user_id).delete()
    return JsonResponse({'status': 'success', 'message': 'Ban revoked'})


@login_required
def get_banned_users(request, meeting_id):
    """Return currently active bans for a meeting."""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    if meeting.teacher != request.user and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'})
    banned = KickedParticipant.objects.filter(meeting=meeting).select_related('user')
    data = [{'id': b.user.id, 'username': b.user.username, 'banned_until': b.banned_until.isoformat()} for b in banned if b.is_banned()]
    return JsonResponse({'banned': data})


@login_required
@require_http_methods(["POST"])
def meeting_global_control(request, meeting_id):
    """Broadcast a global mute-all or camera-off-all control to all participants."""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    if meeting.teacher != request.user and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
    try:
        data = json.loads(request.body)
        control_type = data.get('type')
        value = data.get('value')

        if control_type in ['student_can_view_camera', 'student_can_view_screenshare', 'global_mute', 'global_camera_off', 'global_screenshare_off', 'allow_chat']:
            setattr(meeting, control_type, value)
            meeting.save()

        if control_type == 'allow_chat':
            msg = 'Host has enabled chat for everyone' if value else 'Host has limited chat to host only'
        elif 'student_can_view' in control_type:
            msg = f'Teacher has {"allowed" if value else "blocked"} student {control_type.replace("student_can_view_", "").replace("_", " ")}'
        else:
            msg = f'Teacher has {"enabled" if value else "disabled"} global {control_type.replace("_", " ")}'

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'meeting_{meeting.meeting_code}',
            {'type': 'global_control_update', 'control_type': control_type, 'value': value, 'message': msg}
        )
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
