"""
User profile views: view, edit, directory, search.
Fully integrated with the Centralized Identity System for Admin, Teacher, and Student roles.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.db import models

from accounts.models import UserProfile
from meetings.models import Meeting
from cameras.models import Camera

User = get_user_model()


@login_required
def profile_view(request, username=None):
    """
    Unified Centralized Profile view for Admin, Teacher, and Student.
    Handles viewing and editing own profile or admin editing any profile.
    """
    if username:
        profile_user = get_object_or_404(User, username=username)
    else:
        profile_user = request.user

    is_own_profile = bool(profile_user.id == request.user.id)
    can_edit = bool(is_own_profile or request.user.is_superuser)

    # Ensure profile exists (Centralized Identity Single Source of Truth)
    try:
        profile = profile_user.userprofile
    except UserProfile.DoesNotExist:
        user_type = 'admin' if profile_user.is_superuser else 'student'
        profile = UserProfile.objects.create(
            user=profile_user,
            user_type=user_type,
            is_verified=bool(profile_user.is_superuser)
        )

    if can_edit and request.method == 'POST':
        try:
            from accounts.services import update_user_identity
            update_user_identity(profile_user, request.user, request.POST, request.FILES)
            profile.refresh_from_db()

            # Save achievements if submitted
            achievement_ids = request.POST.getlist('achievement_id[]')
            achievement_titles = request.POST.getlist('achievement_title[]')
            achievement_dates = request.POST.getlist('achievement_date_str[]')
            achievement_descriptions = request.POST.getlist('achievement_description[]')
            achievement_icons = request.POST.getlist('achievement_icon_type[]')

            submitted_ids = []
            from accounts.models import UserAchievement
            for i in range(len(achievement_titles)):
                title = achievement_titles[i].strip()
                if not title:
                    continue

                ach_id = achievement_ids[i].strip() if i < len(achievement_ids) else ""
                date_str = achievement_dates[i].strip() if i < len(achievement_dates) else ""
                description = achievement_descriptions[i].strip() if i < len(achievement_descriptions) else ""
                icon_type = achievement_icons[i].strip() if i < len(achievement_icons) else "award"

                if ach_id and ach_id.isdigit():
                    try:
                        ach = UserAchievement.objects.get(id=int(ach_id), profile=profile)
                        ach.title = title
                        ach.date_str = date_str
                        ach.description = description
                        ach.icon_type = icon_type
                        ach.save()
                        submitted_ids.append(ach.id)
                    except UserAchievement.DoesNotExist:
                        pass
                else:
                    ach = UserAchievement.objects.create(
                        profile=profile,
                        title=title,
                        date_str=date_str,
                        description=description,
                        icon_type=icon_type
                    )
                    submitted_ids.append(ach.id)

            if 'achievement_title[]' in request.POST:
                profile.achievements.exclude(id__in=submitted_ids).delete()

            messages.success(request, 'Profile updated successfully!')
            return redirect('profile_view', username=profile_user.username)
        except Exception as e:
            messages.error(request, f'Error updating profile: {str(e)}')

    # Profile completion score
    completion = 0
    if profile:
        if profile.display_name: completion += 10
        if profile_user.first_name: completion += 10
        if profile_user.last_name: completion += 10
        if profile_user.email: completion += 10
        if profile.bio: completion += 15
        if profile.phone: completion += 10
        if profile.date_of_birth: completion += 10
        if profile.address: completion += 10
        if profile.profile_picture or profile.avatar_url: completion += 15

    completion_dash = int(completion * 2.89)

    # Face verification status for students
    face_registered = False
    try:
        from attendance.models import StudentFaceProfile
        face_registered = StudentFaceProfile.objects.filter(
            student=profile_user,
            is_active=True
        ).exists()
    except Exception:
        pass

    # Role-specific stats calculation
    stats = {}
    is_admin_role = bool(profile_user.is_superuser or (profile and profile.user_type == 'admin'))

    if is_admin_role:
        stats['total_users'] = User.objects.count()
        stats['total_students'] = User.objects.filter(userprofile__user_type='student').count()
        stats['total_teachers'] = User.objects.filter(userprofile__user_type='teacher').count()
        stats['total_meetings'] = Meeting.objects.count()
        stats['live_meetings'] = Meeting.objects.filter(status='live').count()
        stats['total_cameras'] = Camera.objects.count()
    elif profile and profile.user_type == 'teacher':
        stats['total_meetings'] = Meeting.objects.filter(teacher=profile_user, classroom__isnull=True).count()
        stats['live_meetings'] = Meeting.objects.filter(teacher=profile_user, status='live', classroom__isnull=True).count()
        stats['completed_meetings'] = Meeting.objects.filter(teacher=profile_user, status='ended', classroom__isnull=True).count()
        from meetings.models import Classroom, ClassroomMembership
        teacher_classrooms = Classroom.objects.filter(teacher=profile_user)
        stats['total_students'] = ClassroomMembership.objects.filter(
            classroom__in=teacher_classrooms,
            status='approved'
        ).values_list('student', flat=True).distinct().count()
    elif profile and profile.user_type == 'student':
        from meetings.models import ClassroomMembership
        stats['enrolled_courses'] = ClassroomMembership.objects.filter(
            student=profile_user,
            status='approved'
        ).count()
        stats['meetings_attended'] = profile_user.meetingparticipant_set.count()

    # Dynamic EduKarma score for students
    edukarma_score = 0
    if profile and profile.user_type == 'student':
        meetings_count = stats.get('meetings_attended', 0)
        edukarma_score = (completion * 5) + (meetings_count * 50)
        if face_registered:
            edukarma_score += 200

    subjects_list = []
    if profile and profile.subjects:
        if ',' in profile.subjects:
            subjects_list = [s.strip() for s in profile.subjects.split(',') if s.strip()]
        else:
            subjects_list = [s.strip() for s in profile.subjects.split() if s.strip()]

    achievements = profile.achievements.all() if profile else []
    identity = profile.get_identity_dict() if profile else {}

    return render(request, 'accounts/profile/profile.html', {
        'profile_user': profile_user,
        'profile': profile,
        'identity': identity,
        'is_own_profile': is_own_profile,
        'can_edit': can_edit,
        'is_admin_role': is_admin_role,
        'stats': stats,
        'completion': completion,
        'completion_dash': completion_dash,
        'edukarma_score': edukarma_score,
        'face_registered': face_registered,
        'subjects_list': subjects_list,
        'achievements': achievements,
    })


@login_required
def edit_profile(request):
    """Simple edit profile form (alternative to profile_view POST)."""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        user_type = 'admin' if request.user.is_superuser else 'student'
        profile = UserProfile.objects.create(user=request.user, user_type=user_type)

    if request.method == 'POST':
        from accounts.services import update_user_identity
        update_user_identity(request.user, request.user, request.POST, request.FILES)
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile_view', username=request.user.username)

    return render(request, 'accounts/profile/edit_profile.html', {
        'profile': profile,
        'identity': profile.get_identity_dict()
    })


@login_required
def directory(request):
    """View all teachers and students in a searchable directory."""
    query = request.GET.get('q', '').strip()
    user_type = request.GET.get('type', 'all')

    teachers = User.objects.filter(userprofile__user_type='teacher').select_related('userprofile').order_by('username')
    students = User.objects.filter(userprofile__user_type='student').select_related('userprofile').order_by('username')

    if query:
        q_filter = (
            models.Q(username__icontains=query) |
            models.Q(first_name__icontains=query) |
            models.Q(last_name__icontains=query) |
            models.Q(email__icontains=query) |
            models.Q(userprofile__display_name__icontains=query)
        )
        if user_type == 'teacher':
            teachers = teachers.filter(q_filter)
            students = User.objects.none()
        elif user_type == 'student':
            teachers = User.objects.none()
            students = students.filter(q_filter)
        else:
            teachers = teachers.filter(q_filter)
            students = students.filter(q_filter)

    return render(request, 'accounts/messaging/directory.html', {
        'teachers': teachers,
        'students': students,
        'query': query,
        'user_type': user_type
    })


@login_required
def search_users(request):
    """Search for teachers and students (alias to directory)."""
    return directory(request)
