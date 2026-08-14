"""
User profile views: view, edit, directory, search.
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
    """View any user's profile; handles own-profile POST updates."""
    if username:
        profile_user = get_object_or_404(User, username=username)
    else:
        profile_user = request.user

    try:
        profile = profile_user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=profile_user, user_type='admin') if profile_user.is_superuser else None

    is_own_profile = request.user == profile_user

    if is_own_profile and request.method == 'POST':
        try:
            if not profile:
                profile = UserProfile.objects.create(user=request.user, user_type='admin' if request.user.is_superuser else 'teacher')

            request.user.first_name = request.POST.get('first_name', '').strip()
            request.user.last_name = request.POST.get('last_name', '').strip()
            request.user.email = request.POST.get('email', '').strip()
            request.user.save()

            profile.display_name = request.POST.get('display_name', '').strip()
            profile.bio = request.POST.get('bio', '').strip()
            phone_val = (request.POST.get('phone') or request.POST.get('contact_number') or '').strip()
            profile.phone = phone_val
            profile.contact_number = phone_val
            profile.address = request.POST.get('address', '').strip()
            profile.headline = request.POST.get('headline', '').strip()
            profile.subjects = request.POST.get('subjects', '').strip()
            profile.github = request.POST.get('github', '').strip()

            avatar_choice = request.POST.get('avatar_choice', '').strip()
            if request.FILES.get('avatar'):
                profile.profile_picture = request.FILES['avatar']
                profile.avatar_url = None
            elif request.FILES.get('profile_picture'):
                profile.profile_picture = request.FILES['profile_picture']
                profile.avatar_url = None
            elif avatar_choice:
                profile.avatar_url = avatar_choice
                profile.profile_picture = None

            if request.FILES.get('cover_photo'):
                profile.cover_photo = request.FILES['cover_photo']

            dob = request.POST.get('date_of_birth', '').strip()
            profile.date_of_birth = dob if dob else None
            profile.linkedin = request.POST.get('linkedin', '').strip()
            profile.twitter = request.POST.get('twitter', '').strip()
            profile.website = request.POST.get('website', '').strip()

            if profile.user_type == 'student':
                profile.student_id = request.POST.get('student_id', '').strip()
                profile.roll_number = request.POST.get('roll_number', '').strip()
                profile.branch = request.POST.get('branch', '').strip()
                profile.cgpa = request.POST.get('cgpa', '').strip()
                profile.grade = request.POST.get('grade', '').strip()
                enrollment = request.POST.get('enrollment_date', '').strip()
                profile.enrollment_date = enrollment if enrollment else None
            elif profile.user_type == 'teacher':
                profile.employee_id = request.POST.get('employee_id', '').strip()
                profile.department = request.POST.get('department', '').strip()
                profile.specialization = request.POST.get('specialization', '').strip()
                profile.availability_weekday = request.POST.get('availability_weekday', '').strip()
                profile.availability_friday = request.POST.get('availability_friday', '').strip()
                join = request.POST.get('join_date', '').strip()
                profile.join_date = join if join else None

            profile.save()

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

                if ach_id:
                    try:
                        ach = UserAchievement.objects.get(id=ach_id, profile=profile)
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

            profile.achievements.exclude(id__in=submitted_ids).delete()

            messages.success(request, 'Profile updated successfully!')
            return redirect('profile_view', username=request.user.username)
        except Exception as e:
            messages.error(request, f'Error updating profile: {str(e)}')

    # Profile completion score
    completion = 0
    if is_own_profile and profile:
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

    # Correct target user's face registered status
    face_registered = False
    try:
        from attendance.models import StudentFaceProfile
        face_registered = StudentFaceProfile.objects.filter(
            student=profile_user,
            is_active=True
        ).exists()
    except Exception:
        pass

    stats = {}
    if profile_user.is_superuser:
        stats['total_users'] = User.objects.count()
        stats['total_meetings'] = Meeting.objects.count()
        stats['live_meetings'] = Meeting.objects.filter(status='live').count()
        stats['total_cameras'] = Camera.objects.count()
    elif profile and profile.user_type == 'teacher':
        stats['total_meetings'] = Meeting.objects.filter(teacher=profile_user, classroom__isnull=True).count()
        stats['live_meetings'] = Meeting.objects.filter(teacher=profile_user, status='live', classroom__isnull=True).count()
        stats['completed_meetings'] = Meeting.objects.filter(teacher=profile_user, status='ended', classroom__isnull=True).count()
    elif profile and profile.user_type == 'student':
        from meetings.models import ClassroomMembership
        stats['enrolled_courses'] = ClassroomMembership.objects.filter(
            student=profile_user,
            status='approved'
        ).count()
        stats['meetings_attended'] = profile_user.meetingparticipant_set.count()

    # Calculate dynamic EduKarma score for students
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

    return render(request, 'accounts/profile.html', {
        'profile_user': profile_user,
        'profile': profile,
        'is_own_profile': is_own_profile,
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
        profile = UserProfile.objects.create(user=request.user, user_type='student')

    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name', '')
        request.user.last_name = request.POST.get('last_name', '')
        request.user.email = request.POST.get('email', '')
        request.user.save()

        profile.display_name = request.POST.get('display_name', '').strip()
        profile.bio = request.POST.get('bio', '').strip()
        profile.phone = request.POST.get('phone', '').strip()
        profile.contact_number = request.POST.get('phone', '').strip()  # Sync contact_number with phone
        profile.address = request.POST.get('address', '').strip()

        if request.FILES.get('profile_picture'):
            profile.profile_picture = request.FILES['profile_picture']

        dob = request.POST.get('date_of_birth')
        if dob:
            profile.date_of_birth = dob

        profile.linkedin = request.POST.get('linkedin', '').strip()
        profile.twitter = request.POST.get('twitter', '').strip()
        profile.website = request.POST.get('website', '').strip()

        if profile.user_type == 'student':
            profile.student_id = request.POST.get('student_id', '').strip()
            profile.roll_number = request.POST.get('student_id', '').strip()  # Sync roll_number with student_id
            profile.branch = request.POST.get('branch', '').strip()  # Save branch
            profile.grade = request.POST.get('grade', '').strip()
            enrollment = request.POST.get('enrollment_date', '').strip()
            if enrollment:
                profile.enrollment_date = enrollment
        elif profile.user_type == 'teacher':
            profile.employee_id = request.POST.get('employee_id', '')
            profile.department = request.POST.get('department', '')
            profile.specialization = request.POST.get('specialization', '')
            join = request.POST.get('join_date')
            if join:
                profile.join_date = join

        profile.save()
        return redirect('profile_view', username=request.user.username)

    return render(request, 'accounts/edit_profile.html', {'profile': profile})


@login_required
def directory(request):
    """View all teachers and students in a searchable directory."""
    teachers = User.objects.filter(userprofile__user_type='teacher').select_related('userprofile').order_by('username')
    students = User.objects.filter(userprofile__user_type='student').select_related('userprofile').order_by('username')
    return render(request, 'accounts/directory.html', {'teachers': teachers, 'students': students})


@login_required
def search_users(request):
    """Search for teachers and students by name/username/email."""
    query = request.GET.get('q', '').strip()
    user_type = request.GET.get('type', 'all')
    results = []

    if query:
        users = User.objects.filter(
            models.Q(username__icontains=query) |
            models.Q(first_name__icontains=query) |
            models.Q(last_name__icontains=query) |
            models.Q(email__icontains=query) |
            models.Q(userprofile__display_name__icontains=query)
        ).select_related('userprofile').distinct()

        if user_type == 'teacher':
            users = users.filter(userprofile__user_type='teacher')
        elif user_type == 'student':
            users = users.filter(userprofile__user_type='student')
        else:
            users = users.filter(userprofile__user_type__in=['teacher', 'student'])

        results = users[:20]

    return render(request, 'accounts/search_results.html', {
        'query': query, 'user_type': user_type, 'results': results,
    })
