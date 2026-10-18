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
from django.db import transaction
from django.utils import timezone
from accounts.identity import IdentityService

logger = logging.getLogger('attendance')


def _get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def sync_profile_details(u_profile):
    """Profile details are unified via UserProfile canonical SSOT properties."""
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
    roll = request.POST.get('roll_number') or u_profile.roll_number or getattr(request.user, 'username', 'STUDENT')
    branch = request.POST.get('branch') or u_profile.branch or 'GENERAL'
    contact = request.POST.get('contact_number') or u_profile.contact_number

    u_profile.roll_number = roll
    u_profile.branch = branch
    if contact:
        u_profile.contact_number = contact
        u_profile.phone = contact
    u_profile.save()

    algo = result.get('algo') or 'sface_128d'
    encrypted, checksum = svc.prepare_for_storage(result['embedding'], algo=algo)

    StudentFaceProfile.objects.update_or_create(
        student=request.user,
        defaults={
            'face_embedding_encrypted': encrypted, 'embedding_checksum': checksum,
            'face_quality_score': result['quality'], 'is_active': True,
            'consent_version': 'v1.0',
            'consent_at': timezone.now(),
            'enrolled_at': timezone.now(),
            'registration_ip': _get_client_ip(request),
        }
    )
    user_id = request.user.id
    transaction.on_commit(lambda: IdentityService.invalidate_identity_cache(user_id))

    messages.success(request, "✅ Face registered successfully!")
    return redirect('face_setup')


@login_required
@require_POST
def capture_face_photo(request):
    """Handle camera-captured base64 frame for instant government/enterprise-grade face registration."""
    try:
        body = json.loads(request.body)
        frames = body.get('frames_b64') or []
        single_frame = body.get('frame_b64', '')
        if single_frame and single_frame not in frames:
            frames.insert(0, single_frame)

        u_profile = sync_profile_details(request.user.userprofile)
        roll = body.get('roll_number') or u_profile.roll_number or getattr(request.user, 'username', 'STUDENT')
        branch = body.get('branch') or u_profile.branch or 'GENERAL'
        contact = body.get('contact_number') or u_profile.contact_number

        if not frames:
            return JsonResponse({'status': 'error', 'message': 'No frame data received.'}, status=400)

        svc = get_face_service()
        final_embedding = None
        final_quality = 0.0
        final_algo = 'sface_128d'
        error_msg = None

        # Fast-path: extract embedding from the primary frame; if high quality, return immediately!
        for frame_raw in frames[:3]:
            if not frame_raw:
                continue
            b64_str = frame_raw.split(',', 1)[1] if ',' in frame_raw else frame_raw
            try:
                img_bytes = base64.b64decode(b64_str)
            except Exception:
                continue

            res = svc.extract_embedding(img_bytes, live=False)
            if res.get('status') == 'success':
                final_embedding = res['embedding']
                final_quality = float(res.get('quality', 0.8))
                final_algo = res.get('algo') or 'sface_128d'
                # Immediate exit if quality is solid
                if final_quality >= 0.15:
                    break
            elif res.get('status') in ('multiple_faces', 'poor_quality', 'mask_detected', 'sunglasses_detected', 'glasses_detected', 'busy_background', 'poor_lighting'):
                error_msg = res.get('message')
                break

        if not final_embedding:
            msg = error_msg or 'No clear single face detected in captured frame. Please center your face and try again.'
            return JsonResponse({'status': 'error', 'message': msg})

        u_profile.roll_number = roll
        u_profile.branch = branch
        if contact:
            u_profile.contact_number = contact
            u_profile.phone = contact
        u_profile.save()

        encrypted, checksum = svc.prepare_for_storage(final_embedding, algo=final_algo)
        StudentFaceProfile.objects.update_or_create(
            student=request.user,
            defaults={
                'face_embedding_encrypted': encrypted, 'embedding_checksum': checksum,
                'face_quality_score': final_quality, 'is_active': True,
                'consent_version': 'v1.0',
                'consent_at': timezone.now(),
                'enrolled_at': timezone.now(),
                'registration_ip': _get_client_ip(request),
            }
        )
        user_id = request.user.id
        transaction.on_commit(lambda: IdentityService.invalidate_identity_cache(user_id))

        return JsonResponse({
            'status': 'success',
            'quality': final_quality,
            'message': '✅ Face registered successfully!'
        })
    except Exception as exc:
        logger.exception("capture_face_photo error: %s", exc)
        return JsonResponse({'status': 'error', 'message': f'Invalid request data: {exc}'}, status=400)


@login_required
@require_POST
def detect_face(request):
    """
    Lightweight face condition checks for real-time camera feedback:
    evaluates face presence, count, center, size, lighting, blur, and eyes.
    """
    try:
        body = json.loads(request.body)
        b64 = body.get('frame_b64', '')
        if not b64:
            return JsonResponse({'status': 'no_frame', 'message': 'Position your face inside the circle', 'state': 'red'})
        if ',' in b64:
            b64 = b64.split(',', 1)[1]
        image_bytes = base64.b64decode(b64)
    except Exception:
        return JsonResponse({'status': 'invalid_data', 'message': 'Position your face inside the circle', 'state': 'red'})

    import cv2
    import numpy as np

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return JsonResponse({'status': 'decode_error', 'message': 'Position your face inside the circle', 'state': 'red'})

    frame_h, frame_w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    avg_brightness = float(np.mean(gray))

    # Lighting check
    lighting_ok = avg_brightness >= 55
    if not lighting_ok:
        return JsonResponse({
            'status': 'too_dark',
            'message': 'Low lighting — increase room light',
            'state': 'red',
            'checks': {'face': False, 'lighting': False, 'center': False, 'pose': False, 'straight': False, 'eyes': False}
        })

    # Blur check
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blur_ok = laplacian_var >= 32

    # Face detection with Haar Cascade
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(40, 40))

    if len(faces) == 0:
        return JsonResponse({
            'status': 'no_face',
            'message': 'Center face in frame',
            'state': 'red',
            'checks': {'face': False, 'lighting': lighting_ok, 'center': False, 'pose': False, 'straight': False, 'eyes': False}
        })

    if len(faces) > 1:
        return JsonResponse({
            'status': 'multiple_faces',
            'message': 'Multiple faces — single face required',
            'state': 'red',
            'checks': {'face': False, 'lighting': lighting_ok, 'center': False, 'pose': False, 'straight': False, 'eyes': False}
        })

    # Single face geometry check
    (x, y, w, h) = faces[0]
    face_ratio = float(w) / float(frame_w)
    center_x = x + w / 2.0
    center_y = y + h / 2.0
    offset_x = abs(center_x - frame_w / 2.0) / frame_w
    offset_y = abs(center_y - frame_h / 2.0) / frame_h

    centered_ok = (offset_x <= 0.20) and (offset_y <= 0.22)
    too_small = face_ratio < 0.20
    too_big = face_ratio > 0.68

    if too_small:
        return JsonResponse({
            'status': 'too_small',
            'message': 'Move closer',
            'state': 'yellow',
            'checks': {'face': True, 'lighting': lighting_ok, 'center': False, 'pose': True, 'straight': True, 'eyes': True}
        })

    if too_big:
        return JsonResponse({
            'status': 'too_big',
            'message': 'Move back',
            'state': 'yellow',
            'checks': {'face': True, 'lighting': lighting_ok, 'center': False, 'pose': True, 'straight': True, 'eyes': True}
        })

    if not centered_ok:
        return JsonResponse({
            'status': 'not_centered',
            'message': 'Center face in frame',
            'state': 'yellow',
            'checks': {'face': True, 'lighting': lighting_ok, 'center': False, 'pose': True, 'straight': True, 'eyes': True}
        })

    if not blur_ok:
        return JsonResponse({
            'status': 'blurry',
            'message': 'Hold steady',
            'state': 'yellow',
            'checks': {'face': True, 'lighting': lighting_ok, 'center': True, 'pose': True, 'straight': True, 'eyes': False}
        })

    # Eye check in upper face region
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
    face_roi_gray = gray[y:y + int(h * 0.6), x:x + w]
    eyes = eye_cascade.detectMultiScale(face_roi_gray, scaleFactor=1.15, minNeighbors=3, minSize=(15, 15))
    eyes_ok = len(eyes) > 0

    if not eyes_ok:
        return JsonResponse({
            'status': 'eyes_closed_or_masked',
            'message': 'Face covered — remove mask or glasses',
            'state': 'yellow',
            'checks': {'face': True, 'lighting': lighting_ok, 'center': True, 'pose': True, 'straight': True, 'eyes': False}
        })

    # Quality check via face service
    svc = get_face_service()
    res = svc.extract_embedding(image_bytes, live=False)
    quality = res.get('quality', 0.5) if res.get('status') == 'success' else 0.4

    return JsonResponse({
        'status': 'success',
        'message': 'Perfect — hold steady',
        'state': 'green',
        'quality': quality,
        'checks': {'face': True, 'lighting': True, 'center': True, 'pose': True, 'straight': True, 'eyes': True}
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
