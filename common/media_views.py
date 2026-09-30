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
    - face_profiles/: Biometric pictures -> Only self or superuser/admin.
    - assignments/submissions/: Student homework -> Only submitter, teacher, or superuser.
    - chat_files/: Private chat attachments -> Authenticated users only.
    - recordings/: Classroom lectures -> Authenticated users only.
    - avatars / thumbnails / public UI: Accessible to authenticated and unauthenticated viewers.
    """
    clean_path = relative_path.replace('\\', '/').strip('/')

    # 1. Public media (avatars, thumbnails, icons)
    public_prefixes = ('avatars/', 'thumbnails/', 'icons/', 'covers/', 'profile_pictures/')
    if any(clean_path.startswith(p) for p in public_prefixes):
        return True

    # All other media requires authentication
    if not (user and user.is_authenticated):
        return False

    # Superuser has master administrative access
    if user.is_superuser:
        return True

    # 2. Biometric Face Photos (Strict Privacy)
    if clean_path.startswith('face_profiles/'):
        # Check if the photo belongs to the current user
        # Format usually: face_profiles/<username>_... or face_profiles/<user_id>_...
        path_lower = clean_path.lower()
        user_id_str = str(user.id)
        username_str = user.username.lower()
        if f"_{user_id_str}_" in path_lower or f"_{user_id_str}." in path_lower or f"/{username_str}" in path_lower or f"_{username_str}" in path_lower:
            return True
        # Staff/Admins can view for verification
        if getattr(user, 'is_staff', False) or (hasattr(user, 'userprofile') and user.userprofile.user_type == 'admin'):
            return True
        return False

    # 3. Assignment Submissions (Student Privacy)
    if clean_path.startswith('assignments/submissions/') or clean_path.startswith('assignments/assignment_submission/'):
        # Teachers and staff can review
        if getattr(user, 'is_staff', False) or (hasattr(user, 'userprofile') and user.userprofile.user_type in ('teacher', 'admin')):
            return True
        # Check if the submission filename or folder corresponds to this student
        user_id_str = str(user.id)
        username_str = user.username.lower()
        path_lower = clean_path.lower()
        if f"_{user_id_str}_" in path_lower or f"_{username_str}_" in path_lower or f"student_{user_id_str}" in path_lower:
            return True
        return False

    # 4. Recordings, Video Editing & Study Materials
    # Authenticated students and teachers in good standing have access
    return True


def protected_media_serve(request, path):
    """
    Enterprise protected media server with:
    - Path traversal defense
    - Permission checks
    - HTTP Range requests for video/audio seeking
    """
    media_root = os.path.abspath(str(settings.MEDIA_ROOT))
    target_path = os.path.abspath(os.path.join(media_root, path))

    # Path traversal check
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
                return resp

            length = end - start + 1
            response = StreamingHttpResponse(
                file_iterator(target_path, offset=start, length=length),
                status=206,
                content_type=content_type
            )
            response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response['Accept-Ranges'] = 'bytes'
            response['Content-Length'] = str(length)
            return response

    response = StreamingHttpResponse(
        file_iterator(target_path, offset=0, length=file_size),
        content_type=content_type
    )
    response['Accept-Ranges'] = 'bytes'
    response['Content-Length'] = str(file_size)
    return response
