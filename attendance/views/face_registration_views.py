"""
Student face registration views:
face setup page, upload photo, camera capture, detect face, profile info update, status check.
"""
import json
import base64
import logging

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.files.base import ContentFile

from attendance.models import StudentFaceProfile
from attendance.face_service import get_face_service

logger = logging.getLogger('attendance')


def _get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def sync_profile_details(u_profile):
    modified = False
    if not u_profile.roll_number and u_profile.student_id:
        u_profile.roll_number = u_profile.student_id
        modified = True
    elif not u_profile.student_id and u_profile.roll_number:
        u_profile.student_id = u_profile.roll_number
        modified = True

    if not u_profile.contact_number and u_profile.phone:
        u_profile.contact_number = u_profile.phone
        modified = True
    elif not u_profile.phone and u_profile.contact_number:
        u_profile.phone = u_profile.contact_number
        modified = True

    if modified:
        u_profile.save()
    return u_profile


@login_required
def face_setup(request):
    """Landing page for face registration — upload / camera capture tabs."""
    profile = getattr(request.user, 'face_profile', None)
    u_profile = sync_profile_details(request.user.userprofile)
    info_complete = all([u_profile.roll_number, u_profile.branch])
    return render(request, 'attendance/face_setup.html', {
        'has_profile': profile is not None and profile.is_active,
        'profile': profile, 'u_profile': u_profile,
        'info_complete': info_complete, 'page_title': 'Face Registration',
    })


@login_required
@require_POST
def upload_face_photo(request):
    """Handle file-upload approach to face registration."""
    photo = request.FILES.get('photo')
    if not photo:
        messages.error(request, 'Please select a photo.')
        return redirect('face_setup')

    image_bytes = photo.read()
    svc = get_face_service()
    result = svc.extract_embedding(image_bytes)

    if result['status'] != 'success':
        messages.error(request, f"Face detection failed: {result['message']}")
        return redirect('face_setup')

    u_profile = sync_profile_details(request.user.userprofile)
    roll = request.POST.get('roll_number') or u_profile.roll_number
    branch = request.POST.get('branch') or u_profile.branch
    contact = request.POST.get('contact_number') or u_profile.contact_number

    if not all([roll, branch]):
        messages.error(request, 'Student details (Roll, Branch) are missing. Please complete your profile.')
        return redirect('face_setup')

    u_profile.roll_number = roll
    u_profile.branch = branch
    if contact:
        u_profile.contact_number = contact
        u_profile.phone = contact
    u_profile.save()

    encrypted, checksum = svc.prepare_for_storage(result['embedding'])
    photo_file = ContentFile(image_bytes, name=f"{request.user.username}_face.jpg")

    StudentFaceProfile.objects.update_or_create(
        student=request.user,
        defaults={
            'face_embedding_encrypted': encrypted, 'embedding_checksum': checksum,
            'face_quality_score': result['quality'], 'is_active': True,
            'registration_ip': _get_client_ip(request), 'face_photo': photo_file,
        }
    )
    messages.success(request, "✅ Face registered successfully!")
    return redirect('face_setup')


@login_required
@require_POST
def capture_face_photo(request):
    """Handle camera-captured base64 frame for face registration."""
    try:
        body = json.loads(request.body)
        b64 = body.get('frame_b64', '')
        u_profile = sync_profile_details(request.user.userprofile)
        roll = body.get('roll_number') or u_profile.roll_number
        branch = body.get('branch') or u_profile.branch
        contact = body.get('contact_number') or u_profile.contact_number

        if not b64:
            return JsonResponse({'status': 'error', 'message': 'No frame data received.'}, status=400)
        if not all([roll, branch]):
            return JsonResponse({'status': 'error', 'message': 'Student details are missing. Please complete your profile first.'}, status=400)
        if ',' in b64:
            b64 = b64.split(',', 1)[1]
        image_bytes = base64.b64decode(b64)
    except Exception as exc:
        return JsonResponse({'status': 'error', 'message': f'Invalid request data: {exc}'}, status=400)

    svc = get_face_service()
    result = svc.extract_embedding(image_bytes)
    if result['status'] != 'success':
        return JsonResponse({'status': 'error', 'message': result['message']})

    u_profile.roll_number = roll
    u_profile.branch = branch
    if contact:
        u_profile.contact_number = contact
        u_profile.phone = contact
    u_profile.save()

    encrypted, checksum = svc.prepare_for_storage(result['embedding'])
    photo_file = ContentFile(image_bytes, name=f"{request.user.username}_face.jpg")
    StudentFaceProfile.objects.update_or_create(
        student=request.user,
        defaults={
            'face_embedding_encrypted': encrypted, 'embedding_checksum': checksum,
            'face_quality_score': result['quality'], 'is_active': True,
            'registration_ip': _get_client_ip(request), 'face_photo': photo_file,
        }
    )
    return JsonResponse({'status': 'success', 'quality': result['quality'], 'message': '✅ Face registered successfully!'})


@login_required
@require_POST
def detect_face(request):
    """Lightweight face detection for real-time feedback; includes low-light enhancement."""
    try:
        body = json.loads(request.body)
        b64 = body.get('frame_b64', '')
        if not b64:
            return JsonResponse({'status': 'no_frame'})
        if ',' in b64:
            b64 = b64.split(',', 1)[1]
        image_bytes = base64.b64decode(b64)
    except Exception:
        return JsonResponse({'status': 'invalid_data'})

    import cv2
    import numpy as np

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return JsonResponse({'status': 'decode_error'})

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    avg_brightness = np.mean(gray)
    enhanced = False
    if avg_brightness < 60:
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        img_yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV)
        img_yuv[:, :, 0] = clahe.apply(img_yuv[:, :, 0])
        img = cv2.cvtColor(img_yuv, cv2.COLOR_YUV2BGR)
        enhanced = True
        _, buffer = cv2.imencode('.jpg', img)
        image_bytes = buffer.tobytes()

    svc = get_face_service()
    result = svc.extract_embedding(image_bytes, live=False)
    return JsonResponse({
        'status': result['status'], 'quality': result['quality'],
        'low_light_enhanced': enhanced, 'message': result['message'],
    })


@login_required
@require_POST
def update_profile_info(request):
    """AJAX: Update student profile details (roll, branch). Syncs with SSOT IdentityService."""
    try:
        body = json.loads(request.body)
        roll = body.get('roll_number', '').strip()
        branch = body.get('branch', '').strip()
        contact = body.get('contact_number', '').strip()
        if not all([roll, branch]):
            return JsonResponse({'status': 'error', 'message': 'Roll Number and Branch are required.'}, status=400)
            
        profile = request.user.userprofile
        profile.roll_number = roll
        profile.student_id = roll
        profile.branch = branch
        if contact:
            profile.contact_number = contact
            profile.phone = contact
        profile.save()
        
        # Invalidate IdentityService cache to keep SSOT synchronized
        from accounts.identity import IdentityService
        IdentityService.invalidate_identity_cache(request.user.id)
        
        return JsonResponse({'status': 'success', 'message': 'Profile updated successfully.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def face_registration_status(request):
    """AJAX: return whether the current user has an active face profile."""
    profile = getattr(request.user, 'face_profile', None)
    return JsonResponse({
        'registered': profile is not None and profile.is_active,
        'quality': profile.face_quality_score if profile else 0,
        'updated_at': profile.updated_at.isoformat() if profile else None,
    })
