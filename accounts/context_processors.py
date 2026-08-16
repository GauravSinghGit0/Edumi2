import time

def timestamp(request):
    """Add timestamp for cache busting"""
    return {
        'timestamp': int(time.time())
    }

def face_registered(request):
    """Check if current user has registered face ID (for students)"""
    if not request.user.is_authenticated:
        return {'face_registered': False}
    
    try:
        from attendance.models import StudentFaceProfile
        profile = StudentFaceProfile.objects.filter(
            student=request.user,
            is_active=True
        ).first()
        return {'face_registered': profile is not None}
    except Exception:
        return {'face_registered': False}

def user_identity(request):
    """Expose the SSOT user identity to all templates without double resolution."""
    return {
        'user_identity': getattr(request, 'identity', None)
    }
