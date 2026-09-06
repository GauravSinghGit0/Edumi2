"""
Assignment management views:
Teacher: create, list, edit, archive, view submissions, evaluate
Student: list, view detail, submit, view feedback
"""
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages

from meetings.models import Classroom
from assignments.models import Assignment, AssignmentQuestionFile, AssignmentSubmission, AssignmentSubmissionFile
from common.validators import (
    check_uploaded_file,
    sanitize_filename,
    ALLOWED_ASSIGNMENT_EXTENSIONS,
    MAX_ASSIGNMENT_SIZE,
    MAX_SUBMISSION_SIZE,
)


def get_default_due_date():
    """Helper function to get default due date (tomorrow at 23:59)"""
    tomorrow = timezone.now() + timezone.timedelta(days=1)
    return tomorrow.replace(hour=23, minute=59, second=0, microsecond=0)


@login_required
def classroom_assignments(request, classroom_id):
    """View assignments for a classroom (both teacher and student)"""
    classroom = get_object_or_404(Classroom, id=classroom_id)

    # Check access
    is_teacher = (
        hasattr(request.user, 'userprofile') and 
        request.user.userprofile.user_type == 'teacher' and 
        classroom.teacher == request.user
    )
    is_student = (
        hasattr(request.user, 'userprofile') and 
        request.user.userprofile.user_type == 'student' and
        classroom.memberships.filter(student=request.user, status='approved').exists()
    )
    
    if not is_teacher and not is_student:
        messages.error(request, 'You do not have access to this classroom')
        return redirect('student_classrooms')
    
    # Get assignments
    if is_teacher:
        assignments = classroom.assignments.all()
    else:
        assignments = classroom.assignments.filter(status='published')
    
    if is_student:
        # Add submission status for each assignment for the student
        for assignment in assignments:
            assignment.submission_status = assignment.get_submission_status(request.user)
    
    return render(request, 'assignments/classroom_assignments.html', {
        'classroom': classroom,
        'assignments': assignments,
        'is_teacher': is_teacher
    })


@login_required
def create_assignment(request, classroom_id):
    """Teacher creates a new assignment for a classroom"""
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher' or classroom.teacher != request.user:
        messages.error(request, 'Only the classroom teacher can create assignments')
        return redirect('teacher_classrooms')
    
    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        description = (request.POST.get('description') or '').strip()
        instructions = (request.POST.get('instructions') or '').strip()
        total_marks = int(request.POST.get('total_marks', 100))
        due_date_str = request.POST.get('due_date')
        due_time_str = request.POST.get('due_time')
        
        # Parse due date and time
        if due_date_str and due_time_str:
            from datetime import datetime
            due_datetime = datetime.strptime(f"{due_date_str} {due_time_str}", "%Y-%m-%d %H:%M")
            # Make it timezone-aware
            due_date = timezone.make_aware(due_datetime)
        else:
            due_date = get_default_due_date()
        
        # Validate file uploads for question files before proceeding
        files = request.FILES.getlist('question_files')
        for file in files:
            is_valid, err_msg = check_uploaded_file(
                file,
                allowed_extensions=ALLOWED_ASSIGNMENT_EXTENSIONS,
                max_size=MAX_ASSIGNMENT_SIZE,
                file_category="question file"
            )
            if not is_valid:
                messages.error(request, f"File error ({file.name}): {err_msg}")
                return render(request, 'assignments/create_assignment.html', {
                    'classroom': classroom,
                    'default_due_date': due_date_str or get_default_due_date().strftime("%Y-%m-%d"),
                    'default_due_time': due_time_str or "23:59",
                    'title': title,
                    'description': description,
                    'instructions': instructions,
                    'total_marks': total_marks,
                })

        assignment = Assignment.objects.create(
            classroom=classroom,
            title=title,
            description=description,
            instructions=instructions,
            total_marks=total_marks,
            due_date=due_date,
            created_by=request.user
        )
        
        # Save question files
        for file in files:
            clean_name = sanitize_filename(file.name)
            AssignmentQuestionFile.objects.create(
                assignment=assignment,
                file=file,
                filename=clean_name,
                file_type='file'
            )
        
        # Handle links
        link_texts = request.POST.getlist('link_text[]')
        link_urls = request.POST.getlist('link_url[]')
        for text, url in zip(link_texts, link_urls):
            if text.strip() and url.strip():
                AssignmentQuestionFile.objects.create(
                    assignment=assignment,
                    filename=text.strip(),
                    link_url=url.strip(),
                    file_type='link'
                )
        
        # If user clicked "Publish"
        if request.POST.get('action') == 'publish':
            assignment.status = 'published'
            assignment.save()
            messages.success(request, f'Assignment "{title}" published successfully!')
        else:
            messages.success(request, f'Assignment "{title}" saved as draft!')
        
        return redirect('classroom_assignments', classroom_id=classroom_id)
    
    return render(request, 'assignments/create_assignment.html', {
        'classroom': classroom,
        'default_due_date': get_default_due_date().strftime("%Y-%m-%d"),
        'default_due_time': "23:59"
    })


@login_required
def edit_assignment(request, assignment_id):
    """Teacher edits an existing assignment"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher' or assignment.created_by != request.user:
        messages.error(request, 'Only the assignment creator can edit this assignment')
        return redirect('teacher_classrooms')
    
    if request.method == 'POST':
        assignment.title = request.POST.get('title', assignment.title).strip()
        assignment.description = request.POST.get('description', assignment.description).strip()
        assignment.instructions = request.POST.get('instructions', assignment.instructions).strip()
        assignment.total_marks = int(request.POST.get('total_marks', assignment.total_marks))
        
        # Parse due date and time
        due_date_str = request.POST.get('due_date')
        due_time_str = request.POST.get('due_time')
        if due_date_str and due_time_str:
            from datetime import datetime
            due_datetime = datetime.strptime(f"{due_date_str} {due_time_str}", "%Y-%m-%d %H:%M")
            assignment.due_date = timezone.make_aware(due_datetime)
        
        # Handle new file uploads with validation
        files = request.FILES.getlist('question_files')
        for file in files:
            is_valid, err_msg = check_uploaded_file(
                file,
                allowed_extensions=ALLOWED_ASSIGNMENT_EXTENSIONS,
                max_size=MAX_ASSIGNMENT_SIZE,
                file_category="question file"
            )
            if not is_valid:
                messages.error(request, f"File error ({file.name}): {err_msg}")
                return render(request, 'assignments/edit_assignment.html', {
                    'assignment': assignment
                })

        # Handle status change
        action = request.POST.get('action')
        if action == 'publish':
            assignment.status = 'published'
            messages.success(request, f'Assignment "{assignment.title}" published successfully!')
        elif action in ['draft', 'unpublish']:
            assignment.status = 'draft'
            messages.success(request, f'Assignment "{assignment.title}" switched to draft.')
        elif action == 'archive':
            assignment.status = 'archived'
            messages.success(request, f'Assignment "{assignment.title}" archived.')
        elif action == 'delete':
            title = assignment.title
            classroom_id = assignment.classroom.id
            assignment.delete()
            messages.success(request, f'Assignment "{title}" has been permanently deleted.')
            return redirect('classroom_assignments', classroom_id=classroom_id)
        else:
            messages.success(request, f'Assignment "{assignment.title}" updated successfully!')
        
        assignment.save()
        
        # Save valid new files
        for file in files:
            clean_name = sanitize_filename(file.name)
            AssignmentQuestionFile.objects.create(
                assignment=assignment,
                file=file,
                filename=clean_name,
                file_type='file'
            )
        
        # Handle links
        link_texts = request.POST.getlist('link_text[]')
        link_urls = request.POST.getlist('link_url[]')
        for text, url in zip(link_texts, link_urls):
            if text.strip() and url.strip():
                AssignmentQuestionFile.objects.create(
                    assignment=assignment,
                    filename=text.strip(),
                    link_url=url.strip(),
                    file_type='link'
                )
        
        return redirect('classroom_assignments', classroom_id=assignment.classroom.id)
    
    return render(request, 'assignments/edit_assignment.html', {
        'assignment': assignment
    })


@login_required
def delete_assignment(request, assignment_id):
    """Teacher permanently deletes an assignment"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    classroom = assignment.classroom
    
    is_teacher = (
        hasattr(request.user, 'userprofile') and 
        request.user.userprofile.user_type == 'teacher' and 
        (classroom.teacher == request.user or assignment.created_by == request.user)
    )
    if not is_teacher:
        messages.error(request, 'Only the classroom teacher can delete this assignment.')
        return redirect('classroom_assignments', classroom_id=classroom.id)
    
    if request.method == 'POST':
        title = assignment.title
        classroom_id = classroom.id
        assignment.delete()
        messages.success(request, f'Assignment "{title}" has been permanently deleted.')
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'success': True, 'message': f'Assignment "{title}" deleted successfully.'})
        return redirect('classroom_assignments', classroom_id=classroom_id)
    
    return redirect('assignment_detail', assignment_id=assignment.id)


@login_required
def toggle_assignment_status(request, assignment_id):
    """Teacher toggles an assignment between published and draft (unpublish/publish)"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    classroom = assignment.classroom
    
    is_teacher = (
        hasattr(request.user, 'userprofile') and 
        request.user.userprofile.user_type == 'teacher' and 
        (classroom.teacher == request.user or assignment.created_by == request.user)
    )
    if not is_teacher:
        messages.error(request, 'Only the classroom teacher can change the status of this assignment.')
        return redirect('classroom_assignments', classroom_id=classroom.id)
    
    if request.method == 'POST':
        target_status = request.POST.get('target_status')
        if not target_status:
            target_status = 'draft' if assignment.status == 'published' else 'published'
            
        if target_status == 'published':
            assignment.status = 'published'
            messages.success(request, f'Assignment "{assignment.title}" is now published and visible to students!')
        elif target_status in ['draft', 'unpublish']:
            assignment.status = 'draft'
            messages.success(request, f'Assignment "{assignment.title}" has been unpublished (set to draft).')
        elif target_status == 'archived':
            assignment.status = 'archived'
            messages.success(request, f'Assignment "{assignment.title}" has been archived.')
            
        assignment.save()
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'success': True, 'status': assignment.status, 'status_display': assignment.get_status_display()})
            
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
        if next_url:
            return redirect(next_url)
        return redirect('assignment_detail', assignment_id=assignment.id)
    
    return redirect('assignment_detail', assignment_id=assignment.id)


@login_required
def assignment_detail(request, assignment_id):
    """View assignment detail (teacher or student)"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    classroom = assignment.classroom
    
    is_teacher = (
        hasattr(request.user, 'userprofile') and 
        request.user.userprofile.user_type == 'teacher' and 
        classroom.teacher == request.user
    )
    is_student = (
        hasattr(request.user, 'userprofile') and 
        request.user.userprofile.user_type == 'student' and
        classroom.memberships.filter(student=request.user, status='approved').exists()
    )
    
    if not is_teacher and not is_student:
        messages.error(request, 'You do not have access to this assignment')
        return redirect('student_classrooms')
    
    # Get submission stats (for teacher)
    total_students_count = 0
    submitted_count = 0
    not_submitted_count = 0

    if is_teacher:
        total_students_count = classroom.get_approved_memberships().count()
        submitted_count = assignment.submissions.values('student').distinct().count()
        not_submitted_count = max(0, total_students_count - submitted_count)
    
    # Get student's own submission (for student)
    student_submission = None
    if is_student:
        try:
            student_submission = assignment.submissions.get(student=request.user)
        except AssignmentSubmission.DoesNotExist:
            pass
    
    return render(request, 'assignments/assignment_detail.html', {
        'assignment': assignment,
        'classroom': classroom,
        'is_teacher': is_teacher,
        'student_submission': student_submission,
        'total_students_count': total_students_count,
        'submitted_count': submitted_count,
        'not_submitted_count': not_submitted_count,
    })


@login_required
def submit_assignment(request, assignment_id):
    """Student submits an assignment"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    classroom = assignment.classroom
    
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'student':
        messages.error(request, 'Only students can submit assignments')
        return redirect('student_classrooms')
    
    if not classroom.memberships.filter(student=request.user, status='approved').exists():
        messages.error(request, 'You are not approved for this classroom')
        return redirect('student_classrooms')
    
    # Check if already submitted
    existing_submission = AssignmentSubmission.objects.filter(
        assignment=assignment,
        student=request.user
    ).first()
    
    if request.method == 'POST':
        files = request.FILES.getlist('submission_files')
        link_texts = request.POST.getlist('submission_link_text[]')
        link_urls = request.POST.getlist('submission_link_url[]')
        
        has_valid_links = any(t.strip() and u.strip() for t, u in zip(link_texts, link_urls))
        if not files and not has_valid_links and not existing_submission:
            messages.error(request, 'Please select at least one file or add a link to submit.')
            return render(request, 'assignments/submit_assignment.html', {
                'assignment': assignment,
                'existing_submission': existing_submission
            })

        # Validate all submission files before creating/updating record
        for file in files:
            is_valid, err_msg = check_uploaded_file(
                file,
                allowed_extensions=ALLOWED_ASSIGNMENT_EXTENSIONS,
                max_size=MAX_SUBMISSION_SIZE,
                file_category="submission file"
            )
            if not is_valid:
                messages.error(request, f"File error ({file.name}): {err_msg}")
                return render(request, 'assignments/submit_assignment.html', {
                    'assignment': assignment,
                    'existing_submission': existing_submission
                })

        # Create or update submission
        submission, created = AssignmentSubmission.objects.get_or_create(
            assignment=assignment,
            student=request.user
        )

        # On re-submission: trigger save() to update status and updated_at timestamp
        if not created:
            submission.save()

        # Handle file uploads
        for file in files:
            clean_name = sanitize_filename(file.name)
            AssignmentSubmissionFile.objects.create(
                submission=submission,
                file=file,
                filename=clean_name,
                file_type='file'
            )
        
        # Handle links
        for text, url in zip(link_texts, link_urls):
            if text.strip() and url.strip():
                AssignmentSubmissionFile.objects.create(
                    submission=submission,
                    filename=text.strip(),
                    link_url=url.strip(),
                    file_type='link'
                )
        
        messages.success(request, 'Assignment submitted successfully!')
        return redirect('assignment_detail', assignment_id=assignment_id)
    
    return render(request, 'assignments/submit_assignment.html', {
        'assignment': assignment,
        'existing_submission': existing_submission
    })


@login_required
def evaluate_submission(request, submission_id):
    """Teacher evaluates a student's submission"""
    submission = get_object_or_404(AssignmentSubmission, id=submission_id)
    assignment = submission.assignment
    classroom = assignment.classroom
    
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher' or classroom.teacher != request.user:
        messages.error(request, 'Only the classroom teacher can evaluate submissions')
        return redirect('teacher_classrooms')
    
    if request.method == 'POST':
        marks = request.POST.get('marks')
        feedback = request.POST.get('feedback', '')
        
        if marks:
            submission.marks_obtained = int(marks)
        submission.feedback = feedback
        submission.evaluated_at = timezone.now()
        submission.evaluated_by = request.user
        submission.status = 'returned'
        submission.save()
        
        messages.success(request, 'Submission evaluated successfully!')
        return redirect('assignment_detail', assignment_id=assignment.id)
    
    return render(request, 'assignments/evaluate_submission.html', {
        'submission': submission,
        'assignment': assignment,
        'classroom': classroom
    })


@login_required
def delete_question_file(request, file_id):
    """Delete a question file from an assignment"""
    file = get_object_or_404(AssignmentQuestionFile, id=file_id)
    assignment = file.assignment
    classroom = assignment.classroom
    
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher' or assignment.created_by != request.user:
        messages.error(request, 'Only the assignment creator can delete files')
        return JsonResponse({'success': False}, status=403)
    
    # Delete the file from storage
    if file.file and os.path.exists(file.file.path):
        os.remove(file.file.path)
    file.delete()
    return JsonResponse({'success': True})


@login_required
def assignment_submissions(request, assignment_id):
    """Dedicated view for teacher to view and manage all student submissions for an assignment"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    classroom = assignment.classroom

    is_teacher = (
        hasattr(request.user, 'userprofile') and
        request.user.userprofile.user_type == 'teacher' and
        classroom.teacher == request.user
    )
    if not is_teacher:
        messages.error(request, 'Only classroom teachers can view all student submissions.')
        return redirect('assignment_detail', assignment_id=assignment.id)

    approved_students = [m.student for m in classroom.get_approved_memberships()]
    total_students_count = len(approved_students)
    submitted_count = 0
    pending_grade_count = 0
    missing_count = 0
    submissions = []

    for student in approved_students:
        try:
            submission = assignment.submissions.get(student=student)
            submitted_count += 1
            if submission.evaluated_at is None and submission.marks_obtained is None:
                pending_grade_count += 1
            is_late = (
                assignment.due_date and
                submission.submitted_at and
                submission.submitted_at > assignment.due_date
            )
            submissions.append({
                'student': student,
                'submission': submission,
                'status': 'late' if is_late else 'submitted',
                'submitted_at': submission.submitted_at
            })
        except AssignmentSubmission.DoesNotExist:
            is_missing = assignment.due_date and timezone.now() > assignment.due_date
            if is_missing:
                missing_count += 1
            submissions.append({
                'student': student,
                'submission': None,
                'status': 'missing' if is_missing else 'pending',
                'submitted_at': None
            })

    not_submitted_count = max(0, total_students_count - submitted_count)

    return render(request, 'assignments/assignment_submissions.html', {
        'assignment': assignment,
        'classroom': classroom,
        'submissions': submissions,
        'total_students_count': total_students_count,
        'submitted_count': submitted_count,
        'pending_grade_count': pending_grade_count,
        'missing_count': missing_count,
        'not_submitted_count': not_submitted_count,
    })

