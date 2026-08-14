import logging
from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from .models import StudentFaceProfile
from .face_service import get_face_service

User = get_user_model()

logger = logging.getLogger('attendance.tasks')

@shared_task
def process_face_registration(user_id, image_bytes, ip_address):
    """
    Background task to extract embedding from an uploaded photo
    and save it to the student's profile.
    """
    try:
        user = User.objects.get(id=user_id)
        svc = get_face_service()
        
        # 1. Extract embedding
        result = svc.extract_embedding(image_bytes)
        if result['status'] != 'success':
            logger.error(f"Face processing failed for user {user.username}: {result['message']}")
            return False
            
        # 2. Encrypt and save
        encrypted, checksum = svc.prepare_for_storage(result['embedding'])
        photo_file = ContentFile(image_bytes, name=f"{user.username}_face.jpg")
        
        # 3. Update profile
        StudentFaceProfile.objects.update_or_create(
            student=user,
            defaults={
                'face_embedding_encrypted': encrypted,
                'embedding_checksum':       checksum,
                'face_quality_score':       result['quality'],
                'is_active':                True,
                'registration_ip':          ip_address,
                'face_photo':               photo_file,
            }
        )
        return True
    except Exception as e:
        logger.exception(f"Unexpected error in process_face_registration: {e}")
        return False
