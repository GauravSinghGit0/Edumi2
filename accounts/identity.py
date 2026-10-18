"""
accounts/identity.py
Centralized Identification System — Single Source of Truth (SSOT)
Provides canonical identity resolution, caching, batch lookup, authorization boundaries,
and consolidated profile updates across all LMS modules.
"""

import time
import logging
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

logger = logging.getLogger('accounts')
User = get_user_model()

CACHE_TTL = 600  # 10 minutes cache TTL for user identities


class IdentityService:
    """
    Single Source of Truth (SSOT) service for user identity resolution.
    Normalizes credentials, profiles, roles, permissions, and biometric face registration statuses.
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
                'is_active': False,
                'is_deleted': False,
                'avatar_url': 'https://ui-avatars.com/api/?name=Guest&background=e2e8f0&color=64748b&size=200',
                'pfp_url': 'https://ui-avatars.com/api/?name=Guest&background=e2e8f0&color=64748b&size=200',
                'phone': '',
                'contact_number': '',
                'student_id': '',
                'roll_number': '',
                'employee_id': '',
                'department': '',
                'specialization': '',
                'branch': '',
                'grade': '',
                'bio': '',
                'headline': '',
                'face_registered': False,
                'face_registered_at': None,
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

        canonical_student_id = profile.student_id or ''
        canonical_phone = profile.phone or ''
        pfp = profile.get_profile_picture_url()

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
            'is_active': bool(user.is_active),
            'is_deleted': bool(getattr(profile, 'is_deleted', False)),
            'avatar_url': pfp,
            'pfp_url': pfp,
            'phone': canonical_phone,
            'contact_number': canonical_phone,
            'bio': profile.bio or '',
            'headline': profile.headline or '',
            'student_id': canonical_student_id,
            'roll_number': canonical_student_id,
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
                if identity and identity.get('user_id'):
                    results[uid] = identity

        return results

    @staticmethod
    def invalidate_identity_cache(user_id):
        """
        Invalidates the cache entry for a specific user identity.
        """
        if user_id:
            cache.delete(f"user_identity_{user_id}")

    @staticmethod
    def is_identity_visible(actor, target_user):
        """
        Enforce classroom boundaries, role permissions, and privacy for identity lookups.
        - Anonymous or inactive actors cannot look up identities.
        - Admins and superusers can inspect any identity.
        - Users can always inspect their own identity.
        - Teachers can inspect students enrolled in their classrooms, plus fellow faculty/admins.
        - Students can only inspect teachers and fellow students who share an approved classroom.
        """
        if not actor or not actor.is_authenticated or not getattr(actor, 'is_active', True):
            return False

        # Admin / staff override
        if actor.is_superuser or getattr(actor, 'is_staff', False):
            return True
        if hasattr(actor, 'userprofile') and actor.userprofile.user_type == 'admin':
            return True

        # Target ID resolution
        target_id = target_user.id if hasattr(target_user, 'id') else int(target_user)
        if actor.id == target_id:
            return True

        actor_role = getattr(actor, 'userprofile', None) and actor.userprofile.user_type or 'student'

        from meetings.models import Classroom, ClassroomMembership
        from accounts.models import UserProfile

        if actor_role == 'teacher':
            # Check if target is a student in teacher's classrooms
            is_student_in_class = ClassroomMembership.objects.filter(
                classroom__teacher=actor,
                student_id=target_id,
                status='approved'
            ).exists()
            if is_student_in_class:
                return True
            # Or target is a fellow teacher/admin
            target_prof = UserProfile.objects.filter(user_id=target_id).first()
            if target_prof and target_prof.user_type in ('teacher', 'admin'):
                return True
            return False

        elif actor_role == 'student':
            # Check if target is teacher of an approved classroom the student is enrolled in
            is_teacher_of_class = Classroom.objects.filter(
                teacher_id=target_id,
                memberships__student=actor,
                memberships__status='approved'
            ).exists()
            if is_teacher_of_class:
                return True
            # Check if target is a peer student in a shared approved classroom
            shared_classrooms = ClassroomMembership.objects.filter(
                student=actor,
                status='approved'
            ).values_list('classroom_id', flat=True)
            is_peer = ClassroomMembership.objects.filter(
                classroom_id__in=shared_classrooms,
                student_id=target_id,
                status='approved'
            ).exists()
            if is_peer:
                return True
            return False

        return False

    @staticmethod
    def update_identity(target_user, actor, data, files=None):
        """
        Consolidated SSOT service function to update user identity data.
        Enforces authorization, case-insensitive email uniqueness, and identification uniqueness.
        """
        files = files or {}
        if not actor or not actor.is_authenticated or not getattr(actor, 'is_active', True):
            raise PermissionError("Authentication required.")

        is_self = (actor.id == target_user.id)
        is_admin = bool(actor.is_superuser or getattr(actor, 'is_staff', False) or (hasattr(actor, 'userprofile') and actor.userprofile.user_type == 'admin'))

        if not (is_self or is_admin):
            raise PermissionError("You are not authorized to update this user profile.")

        from accounts.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(
            user=target_user,
            defaults={'user_type': 'admin' if target_user.is_superuser else 'student'}
        )

        # 1. Core User model updates
        user_dirty = False
        if 'first_name' in data:
            target_user.first_name = data.get('first_name', '').strip()
            user_dirty = True
        if 'last_name' in data:
            target_user.last_name = data.get('last_name', '').strip()
            user_dirty = True

        if 'email' in data:
            new_email = data.get('email', '').strip().lower()
            if new_email:
                try:
                    validate_email(new_email)
                except ValidationError:
                    raise ValueError("Please provide a valid email address.")
                # Case-insensitive uniqueness check
                if User.objects.filter(email__iexact=new_email).exclude(id=target_user.id).exists():
                    raise ValueError(f"An account with email '{new_email}' already exists.")
            if (target_user.email or '').lower() != new_email:
                target_user.email = new_email
                user_dirty = True
                if not is_admin:
                    profile.is_verified = False
                    profile.email_verified_at = None

        if is_admin:
            if 'is_active' in data:
                target_user.is_active = (str(data['is_active']).lower() in ['true', '1', 'yes', 'on'])
                user_dirty = True
            if 'role' in data and data['role'] in ['student', 'teacher', 'admin']:
                profile.user_type = data['role']
            elif 'user_type' in data and data['user_type'] in ['student', 'teacher', 'admin']:
                profile.user_type = data['user_type']

        if user_dirty:
            target_user.save()

        # 2. Profile personal fields
        if 'display_name' in data:
            profile.display_name = data.get('display_name', '').strip()
        if 'bio' in data:
            profile.bio = data.get('bio', '').strip()

        phone_val = (data.get('phone') or data.get('contact_number') or '').strip()
        if phone_val or 'phone' in data or 'contact_number' in data:
            profile.phone = phone_val or None

        if 'address' in data:
            profile.address = data.get('address', '').strip()
        if 'headline' in data:
            profile.headline = data.get('headline', '').strip()
        if 'subjects' in data:
            profile.subjects = data.get('subjects', '').strip()
        if 'github' in data:
            profile.github = data.get('github', '').strip()
        if 'linkedin' in data:
            profile.linkedin = data.get('linkedin', '').strip()
        if 'twitter' in data:
            profile.twitter = data.get('twitter', '').strip()
        if 'website' in data:
            profile.website = data.get('website', '').strip()

        dob = (data.get('date_of_birth') or '').strip()
        if dob:
            profile.date_of_birth = dob
        elif 'date_of_birth' in data and not dob:
            profile.date_of_birth = None

        # 3. Avatar / Photos
        if files.get('profile_picture'):
            profile.profile_picture = files['profile_picture']
            profile.avatar_url = ''
        elif files.get('avatar'):
            profile.profile_picture = files['avatar']
            profile.avatar_url = ''
        elif data.get('avatar_choice'):
            profile.avatar_url = data['avatar_choice'].strip()
            profile.profile_picture = None

        if files.get('cover_photo'):
            profile.cover_photo = files['cover_photo']

        # 4. Role specific fields & Uniqueness validation
        if profile.user_type == 'student' or is_admin:
            sid = (data.get('student_id') or data.get('roll_number') or '').strip()
            if sid or 'student_id' in data or 'roll_number' in data:
                if sid:
                    if UserProfile.objects.filter(student_id=sid).exclude(user_id=target_user.id).exists():
                        raise ValueError(f"Student ID '{sid}' is already assigned to another user.")
                profile.student_id = sid or None
            if 'branch' in data:
                profile.branch = data.get('branch', '').strip()
            if 'grade' in data:
                profile.grade = data.get('grade', '').strip()
            if 'cgpa' in data:
                profile.cgpa = data.get('cgpa', '').strip()
            enrollment = (data.get('enrollment_date') or '').strip()
            if enrollment:
                profile.enrollment_date = enrollment

        if profile.user_type == 'teacher' or is_admin:
            eid = (data.get('employee_id') or '').strip()
            if eid or 'employee_id' in data:
                if eid:
                    if UserProfile.objects.filter(employee_id=eid).exclude(user_id=target_user.id).exists():
                        raise ValueError(f"Employee ID '{eid}' is already assigned to another user.")
                profile.employee_id = eid or None
            if 'department' in data:
                profile.department = data.get('department', '').strip()
            if 'specialization' in data:
                profile.specialization = data.get('specialization', '').strip()
            if 'availability_weekday' in data:
                profile.availability_weekday = data.get('availability_weekday', '').strip()
            if 'availability_friday' in data:
                profile.availability_friday = data.get('availability_friday', '').strip()
            join = (data.get('join_date') or '').strip()
            if join:
                profile.join_date = join

        profile.save()
        IdentityService.invalidate_identity_cache(target_user.id)
        return IdentityService.get_identity_by_id(target_user.id)
