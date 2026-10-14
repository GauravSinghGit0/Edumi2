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
    """Handle camera-captured base64 frame (or burst of frames) for face registration."""
    try:
        body = json.loads(request.body)
        frames = body.get('frames_b64') or []
        single_frame = body.get('frame_b64', '')
        if single_frame and single_frame not in frames:
            frames.append(single_frame)

        u_profile = sync_profile_details(request.user.userprofile)
        roll = body.get('roll_number') or u_profile.roll_number
        branch = body.get('branch') or u_profile.branch
        contact = body.get('contact_number') or u_profile.contact_number

        if not frames:
            return JsonResponse({'status': 'error', 'message': 'No frame data received.'}, status=400)
        if not all([roll, branch]):
            return JsonResponse({'status': 'error', 'message': 'Student details are missing. Please complete your profile first.'}, status=400)

        svc = get_face_service()
        best_result = None
        best_bytes = None
        best_quality = -1.0

        # Evaluate frames in burst to keep the best one (Requirement 5)
        for frame_raw in frames:
            if not frame_raw:
                continue
            b64_str = frame_raw.split(',', 1)[1] if ',' in frame_raw else frame_raw
            img_bytes = base64.b64decode(b64_str)
            res = svc.extract_embedding(img_bytes)
            if res.get('status') == 'success':
                q = float(res.get('quality', 0.0))
                if q > best_quality:
                    best_quality = q
                    best_result = res
                    best_bytes = img_bytes

        # If none succeeded, fallback to first frame error
        if not best_result:
            first_raw = frames[0]
            b64_str = first_raw.split(',', 1)[1] if ',' in first_raw else first_raw
            first_bytes = base64.b64decode(b64_str)
            best_result = svc.extract_embedding(first_bytes)
            if best_result.get('status') != 'success':
                return JsonResponse({'status': 'error', 'message': best_result.get('message', 'Face registration failed.')})
            best_bytes = first_bytes

        u_profile.roll_number = roll
        u_profile.branch = branch
        if contact:
            u_profile.contact_number = contact
            u_profile.phone = contact
        u_profile.save()

        encrypted, checksum = svc.prepare_for_storage(best_result['embedding'])
        photo_file = ContentFile(best_bytes, name=f"{request.user.username}_face.jpg")
        StudentFaceProfile.objects.update_or_create(
            student=request.user,
            defaults={
                'face_embedding_encrypted': encrypted, 'embedding_checksum': checksum,
                'face_quality_score': best_result.get('quality', 0.0), 'is_active': True,
                'registration_ip': _get_client_ip(request), 'face_photo': photo_file,
            }
        )
        return JsonResponse({
            'status': 'success',
            'quality': best_result.get('quality', 0.0),
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
            'message': 'Find better lighting',
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
            'message': 'Position your face inside the circle',
            'state': 'red',
            'checks': {'face': False, 'lighting': lighting_ok, 'center': False, 'pose': False, 'straight': False, 'eyes': False}
        })

    if len(faces) > 1:
        return JsonResponse({
            'status': 'multiple_faces',
            'message': 'Only one person should be visible',
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
            'message': 'Move back a little',
            'state': 'yellow',
            'checks': {'face': True, 'lighting': lighting_ok, 'center': False, 'pose': True, 'straight': True, 'eyes': True}
        })

    if not centered_ok:
        return JsonResponse({
            'status': 'not_centered',
            'message': 'Center your face in the circle',
            'state': 'yellow',
            'checks': {'face': True, 'lighting': lighting_ok, 'center': False, 'pose': True, 'straight': True, 'eyes': True}
        })

    if not blur_ok:
        return JsonResponse({
            'status': 'blurry',
            'message': 'Hold still',
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
            'message': 'Open your eyes or remove mask / glasses',
            'state': 'yellow',
            'checks': {'face': True, 'lighting': lighting_ok, 'center': True, 'pose': True, 'straight': True, 'eyes': False}
        })

    # Quality check via face service
    svc = get_face_service()
    res = svc.extract_embedding(image_bytes, live=False)
    quality = res.get('quality', 0.5) if res.get('status') == 'success' else 0.4

    return JsonResponse({
        'status': 'success',
        'message': '✨ Perfect! Hold still...',
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
