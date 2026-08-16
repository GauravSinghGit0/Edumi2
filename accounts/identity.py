"""
accounts/identity.py
Centralized Identification System — Single Source of Truth (SSOT)
Provides canonical identity resolution, caching, and batch lookup across all LMS modules.
"""

import time
import logging
from django.core.cache import cache
from django.contrib.auth import get_user_model

logger = logging.getLogger('accounts')
User = get_user_model()

CACHE_TTL = 600  # 10 minutes cache TTL for user identities


class IdentityService:
    """
    Single Source of Truth (SSOT) service for user identity resolution.
    Normalizes credentials, profiles, roles, and biometric face registration statuses.
    """

    @staticmethod
    def get_identity(user):
        """
        Returns standard identity dict for a User object (or AnonymousUser).
        """
        if not user or user.is_anonymous:
            return {
                'user_id': None,
                'username': 'Anonymous',
                'display_name': 'Guest',
                'first_name': '',
                'last_name': '',
                'email': '',
                'role': 'guest',
                'is_verified': False,
                'is_superuser': False,
                'avatar_url': 'https://ui-avatars.com/api/?name=Guest&background=e2e8f0&color=64748b&size=200',
                'phone': '',
                'student_id': '',
                'employee_id': '',
                'department': '',
                'face_registered': False,
                'last_seen': None,
                'version': int(time.time()),
            }

        return IdentityService.get_identity_by_id(user.id)

    @staticmethod
    def get_identity_by_id(user_id):
        """
        Fetch canonical identity dictionary by User ID, backed by cache.
        """
        if not user_id:
            return IdentityService.get_identity(None)

        cache_key = f"user_identity_{user_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            user = User.objects.select_related('userprofile').get(id=user_id)
        except User.DoesNotExist:
            return IdentityService.get_identity(None)

        # Ensure userprofile exists
        from accounts.models import UserProfile
        try:
            profile = user.userprofile
        except UserProfile.DoesNotExist:
            user_type = 'admin' if user.is_superuser else 'student'
            profile = UserProfile.objects.create(
                user=user,
                user_type=user_type,
                is_verified=bool(user.is_superuser)
            )

        # Check face biometric registration status
        face_registered = False
        face_registered_at = None
        try:
            from attendance.models import StudentFaceProfile
            face_prof = StudentFaceProfile.objects.filter(student=user, is_active=True).first()
            if face_prof:
                face_registered = True
                face_registered_at = face_prof.updated_at.isoformat() if hasattr(face_prof, 'updated_at') and face_prof.updated_at else None
        except Exception:
            pass

        identity_dict = {
            'user_id': user.id,
            'username': user.username,
            'display_name': profile.get_display_name(),
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'email': user.email or '',
            'role': profile.user_type,
            'is_verified': bool(profile.is_verified),
            'is_superuser': bool(user.is_superuser),
            'avatar_url': profile.get_profile_picture_url(),
            'phone': profile.phone or profile.contact_number or '',
            'bio': profile.bio or '',
            'headline': profile.headline or '',
            'student_id': profile.student_id or profile.roll_number or '',
            'roll_number': profile.roll_number or profile.student_id or '',
            'branch': profile.branch or '',
            'grade': profile.grade or '',
            'employee_id': profile.employee_id or '',
            'department': profile.department or '',
            'specialization': profile.specialization or '',
            'face_registered': face_registered,
            'face_registered_at': face_registered_at,
            'last_seen': profile.last_seen.isoformat() if profile.last_seen else None,
            'version': int(time.time()),
        }

        cache.set(cache_key, identity_dict, CACHE_TTL)
        return identity_dict

    @staticmethod
    def get_identities_batch(user_ids):
        """
        Batch resolves identity dictionaries for a list of user IDs in 1 query (capped at 100).
        """
        if not user_ids:
            return {}

        # Limit to 100 user IDs per batch request
        clean_ids = list(set([int(uid) for uid in user_ids if str(uid).isdigit()]))[:100]
        if not clean_ids:
            return {}

        results = {}
        missing_ids = []

        for uid in clean_ids:
            cached = cache.get(f"user_identity_{uid}")
            if cached:
                results[uid] = cached
            else:
                missing_ids.append(uid)

        if missing_ids:
            for uid in missing_ids:
                identity = IdentityService.get_identity_by_id(uid)
                results[uid] = identity

        return results

    @staticmethod
    def invalidate_identity_cache(user_id):
        """
        Invalidates the cache entry for a specific user identity.
        """
        if user_id:
            cache.delete(f"user_identity_{user_id}")
