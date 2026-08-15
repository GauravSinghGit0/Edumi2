"""
File upload validation utilities for Edumi2.
Provides extension, MIME type, magic byte (signature), and file size verification.
"""
import os
import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Maximum file sizes (in bytes)
MAX_VIDEO_SIZE = 500 * 1024 * 1024        # 500 MB
MAX_ASSIGNMENT_SIZE = 100 * 1024 * 1024   # 100 MB for teacher question attachments
MAX_SUBMISSION_SIZE = 50 * 1024 * 1024    # 50 MB for student submissions
MAX_IMAGE_SIZE = 10 * 1024 * 1024         # 10 MB for thumbnails/photos
MAX_AUDIO_SIZE = 50 * 1024 * 1024         # 50 MB for audio files

# Allowed extension sets
ALLOWED_VIDEO_EXTENSIONS = {
    'mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v', 'flv', 'wmv'
}

ALLOWED_IMAGE_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'
}

ALLOWED_AUDIO_EXTENSIONS = {
    'mp3', 'wav', 'aac', 'ogg', 'm4a', 'flac', 'wma'
}

ALLOWED_ASSIGNMENT_EXTENSIONS = {
    # Documents
    'pdf', 'doc', 'docx', 'txt', 'rtf', 'odt', 'ppt', 'pptx', 'xls', 'xlsx', 'csv', 'tsv', 'md',
    # Images
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg',
    # Archives
    'zip', 'rar', '7z', 'tar', 'gz',
    # Code files (homework submissions)
    'py', 'java', 'c', 'cpp', 'h', 'hpp', 'cs', 'js', 'ts', 'jsx', 'tsx', 'html', 'css',
    'json', 'sql', 'ipynb', 'r', 'm',
    # Audio / Video (media projects)
    'mp3', 'wav', 'm4a', 'ogg', 'mp4', 'webm', 'mov', 'mkv', 'avi'
}

# Dangerous extensions that should NEVER be allowed under any circumstances
DANGEROUS_EXTENSIONS = {
    'exe', 'bat', 'cmd', 'sh', 'bash', 'zsh', 'php', 'phtml', 'php3', 'php4', 'php5',
    'php7', 'phps', 'cgi', 'pl', 'jsp', 'asp', 'aspx', 'vbs', 'vbe', 'wsf', 'wsh',
    'scr', 'msi', 'dll', 'com', 'hta', 'jar', 'bin', 'app', 'deb', 'rpm', 'ps1', 'psm1',
    'pyc', 'pyo', 'pyd', 'so', 'dylib'
}

# Dangerous executable magic byte signatures
DANGEROUS_MAGIC_SIGNATURES = [
    b'MZ',                           # Windows DOS/PE executable / DLL
    b'\x7fELF',                      # Linux ELF executable/library
    b'\xfe\xed\xfa\xce',             # Mach-O 32-bit (Mac)
    b'\xce\xfa\xed\xfe',             # Mach-O 32-bit (Mac reversed)
    b'\xfe\xed\xfa\xcf',             # Mach-O 64-bit (Mac)
    b'\xcf\xfa\xed\xfe',             # Mach-O 64-bit (Mac reversed)
]


def sanitize_filename(filename):
    """
    Sanitize filename by stripping directory traversal characters and unsafe characters.
    """
    if not filename:
        return "unnamed_file"
    
    # Remove any directory components
    filename = os.path.basename(filename.replace('\\', '/'))
    
    # Replace non-alphanumeric (excluding . - _) with underscore
    name, ext = os.path.splitext(filename)
    clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name)
    clean_ext = re.sub(r'[^a-zA-Z0-9]', '', ext.lower())
    
    if not clean_name:
        clean_name = "file"
    
    return f"{clean_name}.{clean_ext}" if clean_ext else clean_name


def get_file_extension(filename):
    """Extract lowercase file extension without leading dot."""
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[-1].lower()


def read_file_header(file_obj, num_bytes=512):
    """Safely read header bytes from an uploaded file and reset file pointer."""
    try:
        if hasattr(file_obj, 'seek') and hasattr(file_obj, 'read'):
            current_pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
            file_obj.seek(0)
            header = file_obj.read(num_bytes)
            file_obj.seek(current_pos)
            return header
    except Exception:
        pass
    return b''


def check_is_dangerous_content(header):
    """Check if header matches known dangerous executable signatures."""
    if not header:
        return False
    for sig in DANGEROUS_MAGIC_SIGNATURES:
        if header.startswith(sig):
            return True
    return False


def validate_file_signature(header, ext):
    """
    Verify that file header matches the claimed extension for binary types.
    Returns (is_valid, reason).
    """
    if not header:
        return True, ""  # Empty or non-seekable file, rely on extension & content type

    # Check for dangerous executables masquerading under another extension
    if check_is_dangerous_content(header):
        return False, "Executable or binary script files are not allowed."

    ext = ext.lower()

    # PDF signature
    if ext == 'pdf':
        if not header.startswith(b'%PDF-'):
            return False, "File content does not match PDF format."

    # PNG signature
    elif ext == 'png':
        if not header.startswith(b'\x89PNG\r\n\x1a\n'):
            return False, "File content does not match PNG format."

    # JPEG signature
    elif ext in ('jpg', 'jpeg'):
        if not header.startswith(b'\xff\xd8\xff'):
            return False, "File content does not match JPEG format."

    # GIF signature
    elif ext == 'gif':
        if not (header.startswith(b'GIF87a') or header.startswith(b'GIF89a')):
            return False, "File content does not match GIF format."

    # WebP signature: 'RIFF' + 4 bytes + 'WEBP'
    elif ext == 'webp':
        if not (header.startswith(b'RIFF') and len(header) >= 12 and header[8:12] == b'WEBP'):
            return False, "File content does not match WebP format."

    # BMP signature
    elif ext == 'bmp':
        if not header.startswith(b'BM'):
            return False, "File content does not match BMP format."

    # ZIP / DOCX / PPTX / XLSX / JAR
    elif ext in ('zip', 'docx', 'pptx', 'xlsx'):
        if not (header.startswith(b'PK\x03\x04') or header.startswith(b'PK\x05\x06') or header.startswith(b'PK\x07\x08')):
            return False, f"File content does not match {ext.upper()} archive format."

    # MP4 / M4V / MOV: typically contains 'ftyp', 'moov', 'mdat'
    elif ext in ('mp4', 'm4v', 'mov'):
        if len(header) >= 8:
            has_box = (
                b'ftyp' in header[:32] or 
                b'moov' in header[:32] or 
                b'mdat' in header[:32] or 
                b'wide' in header[:32] or
                header.startswith(b'\x00\x00\x00')
            )
            if not has_box:
                return False, "File content does not match MP4/MOV video format."

    # WebM / MKV: Matroska header
    elif ext in ('mkv', 'webm'):
        if not header.startswith(b'\x1a\x45\xdf\xa3'):
            return False, f"File content does not match {ext.upper()} video format."

    # AVI: 'RIFF' + 4 bytes + 'AVI '
    elif ext == 'avi':
        if not (header.startswith(b'RIFF') and len(header) >= 12 and header[8:12] == b'AVI '):
            return False, "File content does not match AVI video format."

    return True, ""


def check_uploaded_file(file_obj, allowed_extensions, max_size, file_category="file"):
    """
    Comprehensive file verification function for views and forms.
    Returns (is_valid: bool, error_message: str or None)
    """
    if not file_obj:
        return False, "No file was provided."

    filename = getattr(file_obj, 'name', '')
    ext = get_file_extension(filename)

    if not ext:
        return False, "Uploaded file has no extension. Please provide a valid file."

    # 1. Blacklist check
    if ext in DANGEROUS_EXTENSIONS:
        return False, f"Files with extension '.{ext}' are not permitted for security reasons."

    # 2. Whitelist check
    if ext not in allowed_extensions:
        allowed_str = ', '.join(sorted([f'.{e}' for e in allowed_extensions]))
        return False, f"Unsupported file type '.{ext}'. Allowed types: {allowed_str}"

    # 3. File size check
    file_size = getattr(file_obj, 'size', None)
    if file_size is not None and file_size > max_size:
        max_mb = max_size // (1024 * 1024)
        return False, f"File size ({file_size / (1024 * 1024):.1f} MB) exceeds maximum allowed size of {max_mb} MB."

    # 4. Header magic byte check
    header = read_file_header(file_obj)
    is_valid_sig, sig_error = validate_file_signature(header, ext)
    if not is_valid_sig:
        return False, sig_error

    return True, None


# ==============================================================================
# DJANGO MODEL & FORM VALIDATORS
# ==============================================================================

def validate_video_file(file_obj):
    """Django validator for video file uploads."""
    is_valid, error = check_uploaded_file(
        file_obj,
        allowed_extensions=ALLOWED_VIDEO_EXTENSIONS,
        max_size=MAX_VIDEO_SIZE,
        file_category="video"
    )
    if not is_valid:
        raise ValidationError(_(error))


def validate_image_file(file_obj):
    """Django validator for image / thumbnail uploads."""
    is_valid, error = check_uploaded_file(
        file_obj,
        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
        max_size=MAX_IMAGE_SIZE,
        file_category="image"
    )
    if not is_valid:
        raise ValidationError(_(error))


def validate_audio_file(file_obj):
    """Django validator for audio uploads."""
    is_valid, error = check_uploaded_file(
        file_obj,
        allowed_extensions=ALLOWED_AUDIO_EXTENSIONS,
        max_size=MAX_AUDIO_SIZE,
        file_category="audio"
    )
    if not is_valid:
        raise ValidationError(_(error))


def validate_assignment_file(file_obj):
    """Django validator for teacher question attachments."""
    is_valid, error = check_uploaded_file(
        file_obj,
        allowed_extensions=ALLOWED_ASSIGNMENT_EXTENSIONS,
        max_size=MAX_ASSIGNMENT_SIZE,
        file_category="assignment file"
    )
    if not is_valid:
        raise ValidationError(_(error))


def validate_assignment_submission_file(file_obj):
    """Django validator for student assignment submission files."""
    is_valid, error = check_uploaded_file(
        file_obj,
        allowed_extensions=ALLOWED_ASSIGNMENT_EXTENSIONS,
        max_size=MAX_SUBMISSION_SIZE,
        file_category="submission file"
    )
    if not is_valid:
        raise ValidationError(_(error))
