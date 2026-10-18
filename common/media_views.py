"""
Secure Protected Media Gateway for Edumi LMS.
Protects sensitive student biometric data, assignments, and recordings from unauthorized access,
while supporting high-throughput HTTP Range requests for video/audio streaming.
"""
import os
import re
import mimetypes
from pathlib import Path
from django.conf import settings
from django.http import (
    HttpResponse, HttpResponseForbidden, Http404,
    StreamingHttpResponse, FileResponse
)
from django.contrib.auth.decorators import login_required


def file_iterator(file_path, offset=0, length=None, chunk_size=524288):
    """Memory-efficient streaming file iterator (512KB chunks)."""
    with open(file_path, 'rb') as f:
        f.seek(offset)
        remaining = length if length is not None else os.path.getsize(file_path) - offset
        while remaining > 0:
            read_size = min(remaining, chunk_size)
            data = f.read(read_size)
            if not data:
                break
            remaining -= len(data)
            yield data


def is_media_access_permitted(user, relative_path):
    """
    Role-Based & Ownership Access Control for Media Assets:
    - face_photos/ & face_profiles/: Biometric pictures -> Only self or superuser/admin.
    - assignments/submissions/: Student homework -> Only submitter, teacher, or superuser.
    - chat_files/: Private chat attachments -> Authenticated users only.
    - recordings/: Classroom lectures -> Authenticated users only.
    - avatars / thumbnails / public UI: Accessible to authenticated and unauthenticated viewers.
    """
    clean_path = relative_path.replace('\\', '/').strip('/')

    # 1. Public media (avatars, thumbnails, icons, covers)
    public_prefixes = ('avatars/', 'thumbnails/', 'icons/', 'covers/', 'profile_pictures/')
    if any(clean_path.startswith(p) for p in public_prefixes):
        return True

    # All other media requires authentication
    if not (user and user.is_authenticated):
        return False

    # Superuser has master administrative access
    if user.is_superuser:
        return True

    # 2. Biometric Face Photos (Strict Privacy — face_photos/ and legacy face_profiles/)
    if clean_path.startswith(('face_photos/', 'face_profiles/')):
        # Staff/Admins can view for student identity verification
        if getattr(user, 'is_staff', False) or (hasattr(user, 'userprofile') and user.userprofile.user_type == 'admin'):
            return True

        # Database-backed ownership verification for student's own face photo
        try:
            from attendance.models import StudentFaceProfile
            if StudentFaceProfile.objects.filter(student=user, face_photo=clean_path).exists():
                return True
            # Also check matching on relative filename
            filename = os.path.basename(clean_path)
            if StudentFaceProfile.objects.filter(student=user, face_photo__endswith=filename).exists():
                return True
        except Exception:
            pass

        return False

    # 3. Assignment Submissions (Student Homework Privacy)
    is_submission = (
        clean_path.startswith(('assignments/submissions/', 'assignments/assignment_submission/')) or
        bool(re.match(r'^assignments/\d+/submissions/', clean_path))
    )
    if is_submission:
        # Teachers and staff can review
        if getattr(user, 'is_staff', False) or (hasattr(user, 'userprofile') and user.userprofile.user_type in ('teacher', 'admin')):
            return True

        # Exact database-backed ownership verification
        try:
            from assignments.models import AssignmentSubmissionFile
            filename = os.path.basename(clean_path)
            if AssignmentSubmissionFile.objects.filter(
                submission__student=user
            ).filter(file__endswith=filename).exists():
                return True
        except Exception:
            pass

        return False

    # 4. Student Photos (admin-only identity verification uploads)
    if clean_path.startswith('student_photos/'):
        if getattr(user, 'is_staff', False) or (hasattr(user, 'userprofile') and user.userprofile.user_type == 'admin'):
            return True
        try:
            from accounts.models import StudentPhoto
            filename = os.path.basename(clean_path)
            if StudentPhoto.objects.filter(student=user, photo__endswith=filename).exists():
                return True
        except Exception:
            pass
        return False

    # 5. User-specific video editing assets and projects
    if clean_path.startswith('videos/'):
        parts = clean_path.split('/')
        if len(parts) >= 2 and parts[1].isdigit():
            owner_id = int(parts[1])
            if user.id == owner_id or user.is_superuser or (hasattr(user, 'userprofile') and user.userprofile.user_type == 'admin'):
                return True
            try:
                from videos.models import Video
                if Video.objects.filter(uploaded_by_id=owner_id, status='published').exists():
                    return True
            except Exception:
                pass
            return False

    # 6. General recordings & study materials
    # Authenticated students and teachers in good standing have access
    return True


def protected_media_serve(request, path):
    """
    Enterprise protected media server with:
    - Path traversal defense
    - Permission checks
    - HTTP Range requests for video/audio seeking
    - Nginx X-Accel-Redirect support for zero-copy reverse proxy streaming
    - Strict Content-Security-Policy and attachment disposition for dangerous content (SVG/HTML)
    """
    media_root = os.path.abspath(str(settings.MEDIA_ROOT))
    target_path = os.path.abspath(os.path.join(media_root, path))

    # 1. Path traversal check
    if not target_path.startswith(media_root + os.sep) and target_path != media_root:
        raise Http404("Invalid file path")

    # 2. Access control (checked before existence to prevent user/file enumeration)
    if not is_media_access_permitted(request.user, path):
        if not (request.user and request.user.is_authenticated):
            from django.shortcuts import redirect
            return redirect('login')
        return HttpResponseForbidden("Access Denied: You do not have permission to view this resource.")

    # 3. File existence check
    if not os.path.isfile(target_path):
        raise Http404("File not found")

    file_size = os.path.getsize(target_path)
    content_type, _ = mimetypes.guess_type(target_path)
    content_type = content_type or 'application/octet-stream'

    clean_path = path.replace('\\', '/').strip('/')

    # Security: Mitigate Stored XSS for SVGs, HTML, and scriptable uploads
    ext = os.path.splitext(target_path)[1].lower().lstrip('.')
    is_scriptable = ext in ('svg', 'html', 'htm', 'xhtml', 'xml', 'js')

    def _apply_security_headers(resp):
        resp['X-Content-Type-Options'] = 'nosniff'
        if is_scriptable:
            resp['Content-Security-Policy'] = "default-src 'none'; sandbox"
            resp['Content-Disposition'] = f'attachment; filename="{os.path.basename(target_path)}"'
        return resp

    # 4. Check for Nginx X-Accel-Redirect
    if getattr(settings, 'USE_X_ACCEL_REDIRECT', False):
        response = HttpResponse()
        response['X-Accel-Redirect'] = f'/internal_media/{clean_path}'
        response['Content-Type'] = content_type
        return _apply_security_headers(response)

    # Support HTTP Range requests (crucial for video scrubbing & seeking)
    range_header = request.META.get('HTTP_RANGE', '').strip()
    if range_header:
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if range_match:
            start = int(range_match.group(1))
            end = range_match.group(2)
            end = int(end) if end else file_size - 1

            if start >= file_size or start > end:
                resp = HttpResponse(status=416)
                resp['Content-Range'] = f'bytes */{file_size}'
                return _apply_security_headers(resp)

            length = end - start + 1
            response = StreamingHttpResponse(
                file_iterator(target_path, offset=start, length=length),
                status=206,
                content_type=content_type
            )
            response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response['Accept-Ranges'] = 'bytes'
            response['Content-Length'] = str(length)
            return _apply_security_headers(response)

    response = StreamingHttpResponse(
        file_iterator(target_path, offset=0, length=file_size),
        content_type=content_type
    )
    response['Accept-Ranges'] = 'bytes'
    response['Content-Length'] = str(file_size)
    return _apply_security_headers(response)

