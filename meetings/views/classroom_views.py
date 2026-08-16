"""
Classroom management views:
create, list, join, approve/deny/remove students, delete, leave, start meeting.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password

from meetings.models import Classroom, ClassroomMembership, Meeting
from accounts.notification_utils import (
    notify_classroom_join_request,
    notify_classroom_request_approved,
    notify_student_joined_classroom,
    notify_classroom_request_denied,
    notify_student_removed_from_classroom,
    notify_meeting_started,
)
from .meeting_views import generate_meeting_code


@login_required
def create_classroom(request):
    """Teacher creates a new classroom."""
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher':
        messages.error(request, 'Only teachers can create classrooms')
        return redirect('login')

    if request.method == 'POST':
        class_code = (request.POST.get('class_code') or '').strip().upper()
        title = (request.POST.get('title') or '').strip()
        password = request.POST.get('password')
        description = (request.POST.get('description') or '').strip()

        if Classroom.objects.filter(class_code=class_code).exists():
            messages.error(request, 'Class code already exists. Please choose a different one.')
            # Store form data in session for repopulation
            request.session['classroom_form_data'] = {
                'class_code': class_code,
                'title': title,
                'description': description
            }
            return redirect('create_classroom')

        classroom = Classroom.objects.create(
            class_code=class_code,
            title=title,
            password=make_password(password),
            teacher=request.user,
            description=description
        )
        # Initialize classroom group conversation
        classroom.get_or_create_conversation()

        # Clear any stored form data
        if 'classroom_form_data' in request.session:
            del request.session['classroom_form_data']
        messages.success(request, f'Classroom "{title}" created successfully! Share code: {class_code}')
        return redirect('teacher_classrooms')

    # Retrieve stored form data if available
    form_data = request.session.get('classroom_form_data', {})
    if 'classroom_form_data' in request.session:
        del request.session['classroom_form_data']
    return render(request, 'meetings/classroom/create_classroom.html', {'form_data': form_data})


@login_required
def teacher_classrooms(request):
    """Teacher views all their classrooms."""
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher':
        return redirect('login')
    classrooms = Classroom.objects.filter(teacher=request.user, is_active=True)
    return render(request, 'meetings/classroom/teacher_classrooms.html', {'classrooms': classrooms})


@login_required
def classroom_detail(request, classroom_id):
    """View classroom details with pending requests and approved students."""
    classroom = get_object_or_404(Classroom, id=classroom_id)
    from meetings.services import get_classroom_detail_context
    ctx = get_classroom_detail_context(classroom, request.user)
    if ctx is None:
        messages.error(request, 'You do not have access to this classroom')
        return redirect('student_classrooms')
    return render(request, 'meetings/classroom/classroom_detail.html', ctx)


@login_required
def join_classroom_request(request):
    """Student submits request to join a classroom."""
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'student':
        messages.error(request, 'Only students can join classrooms')
        return redirect('login')

    if request.method == 'POST':
        class_code = (request.POST.get('class_code') or '').strip().upper()
        password = request.POST.get('password')

        try:
            classroom = Classroom.objects.get(class_code=class_code, is_active=True)
        except Classroom.DoesNotExist:
            messages.error(request, 'Invalid class code')
            # Store form data in session
            request.session['join_classroom_form_data'] = {'class_code': class_code}
            return redirect('join_classroom_request')

        if not check_password(password, classroom.password):
            messages.error(request, 'Incorrect password')
            request.session['join_classroom_form_data'] = {'class_code': class_code}
            return redirect('join_classroom_request')

        existing_membership = ClassroomMembership.objects.filter(
            classroom=classroom, student=request.user
        ).first()

        if existing_membership:
            if existing_membership.status == 'approved':
                messages.info(request, 'You are already a member of this classroom')
                return redirect('classroom_detail', classroom_id=classroom.id)
            elif existing_membership.status == 'pending':
                messages.info(request, 'Your join request is pending approval')
                return redirect('student_classrooms')
            elif existing_membership.status == 'denied':
                messages.error(request, 'Your previous request was denied. Please contact the teacher.')
                return redirect('student_classrooms')

        ClassroomMembership.objects.create(
            classroom=classroom, student=request.user, status='pending'
        )
        notify_classroom_join_request(request.user, classroom)
        messages.success(request, f'Join request submitted for "{classroom.title}". Waiting for teacher approval.')
        return redirect('student_classrooms')

    # Retrieve stored form data if available
    form_data = request.session.get('join_classroom_form_data', {})
    if 'join_classroom_form_data' in request.session:
        del request.session['join_classroom_form_data']
    return render(request, 'meetings/classroom/join_classroom.html', {'form_data': form_data})


@login_required
def student_classrooms(request):
    """Student views all their classrooms."""
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'student':
        return redirect('login')

    approved_memberships = ClassroomMembership.objects.filter(
        student=request.user, status='approved'
    ).select_related('classroom')
    pending_memberships = ClassroomMembership.objects.filter(
        student=request.user, status='pending'
    ).select_related('classroom')

    return render(request, 'meetings/classroom/student_classrooms.html', {
        'approved_memberships': approved_memberships,
        'pending_memberships': pending_memberships,
    })


@login_required
@require_http_methods(["POST"])
def approve_join_request(request, membership_id):
    """Teacher approves a student's join request."""
    membership = get_object_or_404(ClassroomMembership, id=membership_id)
    if membership.classroom.teacher != request.user:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'})
    membership.status = 'approved'
    membership.approved_at = timezone.now()
    membership.approved_by = request.user
    membership.save()
    
    # Sync student to classroom conversation
    conv = membership.classroom.get_or_create_conversation()
    conv.participants.add(membership.student)

    notify_classroom_request_approved(membership.student, membership.classroom, request.user)
    notify_student_joined_classroom(membership.student, membership.classroom)
    return JsonResponse({'status': 'success', 'message': f'{membership.student.username} approved'})


@login_required
@require_http_methods(["POST"])
def deny_join_request(request, membership_id):
    """Teacher denies a student's join request."""
    membership = get_object_or_404(ClassroomMembership, id=membership_id)
    if membership.classroom.teacher != request.user:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'})
    membership.status = 'denied'
    membership.save()
    notify_classroom_request_denied(membership.student, membership.classroom)
    return JsonResponse({'status': 'success', 'message': f'{membership.student.username} denied'})


@login_required
@require_http_methods(["POST"])
def remove_student(request, membership_id):
    """Teacher removes a student from classroom."""
    membership = get_object_or_404(ClassroomMembership, id=membership_id)
    if membership.classroom.teacher != request.user:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'})
    membership.status = 'removed'
    membership.save()
    
    # Remove student from classroom conversation
    conv = membership.classroom.get_or_create_conversation()
    conv.participants.remove(membership.student)

    notify_student_removed_from_classroom(membership.student, membership.classroom)
    return JsonResponse({'status': 'success', 'message': f'{membership.student.username} removed from classroom'})


@login_required
@require_http_methods(["POST"])
def delete_classroom(request, classroom_id):
    """Teacher deletes a classroom."""
    classroom = get_object_or_404(Classroom, id=classroom_id)
    if classroom.teacher != request.user:
        messages.error(request, 'Only the classroom teacher can delete this classroom')
        return redirect('classroom_detail', classroom_id=classroom_id)
    if classroom.has_active_meeting():
        messages.error(request, 'Cannot delete classroom with an active meeting. End the meeting first.')
        return redirect('classroom_detail', classroom_id=classroom_id)
    title = classroom.title
    classroom.delete()
    messages.success(request, f'Classroom "{title}" has been deleted successfully')
    return redirect('teacher_classrooms')


@login_required
@require_http_methods(["POST"])
def leave_classroom(request, classroom_id):
    """Student leaves a classroom."""
    classroom = get_object_or_404(Classroom, id=classroom_id)
    try:
        membership = ClassroomMembership.objects.get(
            classroom=classroom, student=request.user, status='approved'
        )
    except ClassroomMembership.DoesNotExist:
        messages.error(request, 'You are not a member of this classroom')
        return redirect('student_classrooms')
    membership.status = 'left'
    membership.save()
    
    # Remove student from classroom conversation
    conv = classroom.get_or_create_conversation()
    conv.participants.remove(request.user)

    messages.success(request, f'You have left "{classroom.title}"')
    return redirect('student_classrooms')


@login_required
def start_classroom_meeting(request, classroom_id):
    """Teacher starts a new meeting in the classroom."""
    classroom = get_object_or_404(Classroom, id=classroom_id)
    if classroom.teacher != request.user:
        messages.error(request, 'Only the classroom teacher can start meetings')
        return redirect('classroom_detail', classroom_id=classroom_id)

    if classroom.has_active_meeting():
        active_meeting = classroom.get_active_meeting()
        messages.info(request, 'A meeting is already in progress')
        return redirect('join_meeting', meeting_code=active_meeting.meeting_code)

    if request.method == 'POST':
        title = request.POST.get('title', classroom.title).strip()
        duration_minutes = int(request.POST.get('duration_minutes', 60))
        allow_screen_share = request.POST.get('allow_screen_share', 'on') == 'on'
        allow_chat = request.POST.get('allow_chat', 'on') == 'on'
        record_meeting = request.POST.get('record_meeting') == 'on'

        if not title:
            messages.error(request, 'Meeting title cannot be empty.')
            return render(request, 'meetings/live/start_classroom_meeting.html', {'classroom': classroom})

        if Meeting.objects.filter(
            classroom=classroom, title__iexact=title
        ).exclude(status__in=['ended', 'cancelled']).exists():
            messages.error(request, f'A meeting named "{title}" already exists in this classroom.')
            return render(request, 'meetings/live/start_classroom_meeting.html', {'classroom': classroom})

        meeting = Meeting.objects.create(
            classroom=classroom,
            title=title,
            teacher=request.user,
            meeting_type='classroom',
            meeting_code=generate_meeting_code(),
            scheduled_time=timezone.now(),
            duration_minutes=duration_minutes,
            status='live',
            allow_screen_share=allow_screen_share,
            allow_chat=allow_chat,
            record_meeting=record_meeting,
        )
        notify_meeting_started(meeting, classroom)
        messages.success(request, 'Meeting started successfully!')
        return redirect('join_meeting', meeting_code=meeting.meeting_code)

    return render(request, 'meetings/live/start_classroom_meeting.html', {'classroom': classroom})


@login_required
def api_classrooms(request):
    """API endpoint returning JSON list of classrooms for current user."""
    if hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'teacher':
        classrooms = Classroom.objects.filter(teacher=request.user, is_active=True)
    else:
        memberships = ClassroomMembership.objects.filter(student=request.user, status='approved')
        classrooms = Classroom.objects.filter(id__in=memberships.values_list('classroom_id', flat=True), is_active=True)
    
    data = [{'id': c.id, 'title': c.title, 'class_code': c.class_code} for c in classrooms]
    return JsonResponse(data, safe=False)
