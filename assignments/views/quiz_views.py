"""
Quiz management views:
Teacher: create, list, edit, archive, view submissions, evaluate
Student: list, view detail, submit, view feedback
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages
from django.db import models
from django.db.models import Q, Count

from meetings.models import Classroom
from assignments.models import Quiz, Question, Choice, QuizSubmission, StudentAnswer


@login_required
def classroom_quizzes(request, classroom_id):
    """View quizzes for a classroom (both teacher and student)"""
    classroom = get_object_or_404(Classroom, id=classroom_id)

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
    
    submitted_quiz_ids = set()
    if is_teacher:
        quizzes = classroom.quizzes.all()
    else:
        # Students only see published quizzes that have at least 1 question and whose due_date has not passed
        now = timezone.now()
        quizzes = classroom.quizzes.filter(status='published').annotate(
            question_count=Count('questions')
        ).filter(
            question_count__gt=0
        ).filter(
            Q(due_date__gte=now) | Q(due_date__isnull=True)
        )
        submitted_quiz_ids = set(
            QuizSubmission.objects.filter(quiz__classroom=classroom, student=request.user)
            .values_list('quiz_id', flat=True)
        )
    
    return render(request, 'quizzes/classroom_quizzes.html', {
        'classroom': classroom,
        'quizzes': quizzes,
        'is_teacher': is_teacher,
        'is_student': is_student,
        'submitted_quiz_ids': submitted_quiz_ids
    })


@login_required
def create_quiz(request, classroom_id):
    """Teacher creates a new quiz for a classroom"""
    classroom = get_object_or_404(Classroom, id=classroom_id)

    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher' or classroom.teacher != request.user:
        messages.error(request, 'Only the classroom teacher can create quizzes')
        return redirect('teacher_classrooms')
    
    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        description = (request.POST.get('description') or '').strip()
        total_marks = int(request.POST.get('total_marks', 100))
        time_limit = request.POST.get('time_limit')
        time_limit = int(time_limit) if time_limit else None
        due_date_str = request.POST.get('due_date')
        due_time_str = request.POST.get('due_time')
        
        due_date = None
        if due_date_str and due_time_str:
            from datetime import datetime
            due_datetime = datetime.strptime(f"{due_date_str} {due_time_str}", "%Y-%m-%d %H:%M")
            due_date = timezone.make_aware(due_datetime)
        
        # Always create newly made quizzes as draft so students don't see an empty quiz
        quiz = Quiz.objects.create(
            classroom=classroom,
            title=title,
            description=description,
            total_marks=total_marks,
            time_limit=time_limit,
            due_date=due_date,
            status='draft',
            created_by=request.user
        )
        
        messages.success(request, f'Quiz "{title}" created as draft! Please add questions before publishing.')
        return redirect('edit_quiz', quiz_id=quiz.id)
    
    return render(request, 'quizzes/create_quiz.html', {
        'classroom': classroom,
        'default_due_date': (timezone.now() + timezone.timedelta(days=1)).strftime("%Y-%m-%d"),
        'default_due_time': "23:59"
    })


@login_required
def edit_quiz(request, quiz_id):
    """Teacher edits an existing quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher' or quiz.created_by != request.user:
        messages.error(request, 'Only the quiz creator can edit this quiz')
        return redirect('teacher_classrooms')
    
    if request.method == 'POST':
        quiz.title = request.POST.get('title', quiz.title).strip()
        quiz.description = request.POST.get('description', quiz.description).strip()
        quiz.total_marks = int(request.POST.get('total_marks', quiz.total_marks))
        
        time_limit = request.POST.get('time_limit')
        quiz.time_limit = int(time_limit) if time_limit else None
        
        due_date_str = request.POST.get('due_date')
        due_time_str = request.POST.get('due_time')
        if due_date_str and due_time_str:
            from datetime import datetime
            due_datetime = datetime.strptime(f"{due_date_str} {due_time_str}", "%Y-%m-%d %H:%M")
            quiz.due_date = timezone.make_aware(due_datetime)
        
        action = request.POST.get('action')
        if action == 'publish':
            if quiz.questions.count() == 0:
                messages.error(request, 'Cannot publish a quiz with no questions. Please add at least one question first.')
                return redirect('edit_quiz', quiz_id=quiz.id)
            quiz.status = 'published'
            messages.success(request, f'Quiz "{quiz.title}" published to classroom students!')
        elif action in ['draft', 'unpublish']:
            quiz.status = 'draft'
            messages.success(request, f'Quiz "{quiz.title}" switched to draft (hidden from classroom students).')
        elif action == 'archive':
            quiz.status = 'archived'
            messages.success(request, f'Quiz "{quiz.title}" archived.')
        elif action == 'delete':
            title = quiz.title
            classroom_id = quiz.classroom.id
            quiz.delete()
            messages.success(request, f'Quiz "{title}" has been permanently deleted.')
            return redirect('classroom_quizzes', classroom_id=classroom_id)
        else:
            messages.success(request, f'Quiz "{quiz.title}" updated successfully!')
        
        quiz.save()
        return redirect('edit_quiz', quiz_id=quiz.id)
    
    total_question_marks = sum(q.marks for q in quiz.questions.all())
    
    return render(request, 'quizzes/edit_quiz.html', {
        'quiz': quiz,
        'total_question_marks': total_question_marks
    })


@login_required
def delete_quiz(request, quiz_id):
    """Teacher permanently deletes a quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    classroom = quiz.classroom
    
    is_teacher = (
        hasattr(request.user, 'userprofile') and 
        request.user.userprofile.user_type == 'teacher' and 
        (classroom.teacher == request.user or quiz.created_by == request.user)
    )
    if not is_teacher:
        messages.error(request, 'Only the classroom teacher can delete this quiz.')
        return redirect('classroom_quizzes', classroom_id=classroom.id)
    
    if request.method == 'POST':
        title = quiz.title
        classroom_id = classroom.id
        quiz.delete()
        messages.success(request, f'Quiz "{title}" has been permanently deleted.')
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'success': True, 'message': f'Quiz "{title}" deleted successfully.'})
        return redirect('classroom_quizzes', classroom_id=classroom_id)
    
    return redirect('quiz_detail', quiz_id=quiz.id)


@login_required
def toggle_quiz_status(request, quiz_id):
    """Teacher toggles a quiz between published and draft (unpublish/publish)"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    classroom = quiz.classroom
    
    is_teacher = (
        hasattr(request.user, 'userprofile') and 
        request.user.userprofile.user_type == 'teacher' and 
        (classroom.teacher == request.user or quiz.created_by == request.user)
    )
    if not is_teacher:
        messages.error(request, 'Only the classroom teacher can change the status of this quiz.')
        return redirect('classroom_quizzes', classroom_id=classroom.id)
    
    if request.method == 'POST':
        target_status = request.POST.get('target_status')
        if not target_status:
            target_status = 'draft' if quiz.status == 'published' else 'published'
            
        if target_status == 'published':
            if quiz.questions.count() == 0:
                messages.error(request, 'Cannot publish a quiz with no questions. Please add at least 1 question first.')
                return redirect('edit_quiz', quiz_id=quiz.id)
            quiz.status = 'published'
            messages.success(request, f'Quiz "{quiz.title}" is now published and visible to students!')
        elif target_status in ['draft', 'unpublish']:
            quiz.status = 'draft'
            messages.success(request, f'Quiz "{quiz.title}" has been unpublished (set to draft).')
        elif target_status == 'archived':
            quiz.status = 'archived'
            messages.success(request, f'Quiz "{quiz.title}" has been archived.')
            
        quiz.save()
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'success': True, 'status': quiz.status, 'status_display': quiz.get_status_display()})
            
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
        if next_url:
            return redirect(next_url)
        return redirect('quiz_detail', quiz_id=quiz.id)
    
    return redirect('quiz_detail', quiz_id=quiz.id)


@login_required
def quiz_detail(request, quiz_id):
    """View quiz detail (teacher or student)"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    classroom = quiz.classroom
    
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
        messages.error(request, 'You do not have access to this quiz')
        return redirect('student_classrooms')

    # Students cannot see draft quizzes unless they already participated (e.g. in live meeting)
    if is_student and quiz.status != 'published':
        has_sub = quiz.submissions.filter(student=request.user).exists()
        if not has_sub:
            messages.error(request, 'This quiz is not published yet.')
            return redirect('classroom_quizzes', classroom_id=classroom.id)

    # Students who haven't submitted yet should go directly to take_quiz, not see all questions here
    if is_student:
        has_submitted = quiz.submissions.filter(student=request.user).exists()
        if not has_submitted:
            return redirect('take_quiz', quiz_id=quiz_id)
    
    submissions = []
    total_students_count = 0
    submitted_count = 0
    graded_count = 0
    pending_grade_count = 0
    missing_count = 0
    average_score = None
    submission_rate = 0
    
    if is_teacher:
        approved_students = [m.student for m in classroom.get_approved_memberships()]
        total_students_count = len(approved_students)
        
        for student in approved_students:
            # Use filter().order_by().first() to safely handle multi-mode submissions
            submission = quiz.submissions.filter(student=student).order_by('-submitted_at').first()
            if submission:
                submissions.append({
                    'student': student,
                    'submission': submission,
                    'status': 'submitted'
                })
                submitted_count += 1
                if submission.marks_obtained is not None:
                    graded_count += 1
                else:
                    pending_grade_count += 1
            else:
                is_missing = quiz.due_date and timezone.now() > quiz.due_date
                if is_missing:
                    missing_count += 1
                submissions.append({
                    'student': student,
                    'submission': None,
                    'status': 'missing' if is_missing else 'pending'
                })
        
        graded_scores = [
            s['submission'].marks_obtained for s in submissions 
            if s['submission'] and s['submission'].marks_obtained is not None
        ]
        if graded_scores and quiz.total_marks > 0:
            average_score = round(sum(graded_scores) / len(graded_scores), 1)
            
        if total_students_count > 0:
            submission_rate = round((submitted_count / total_students_count) * 100)
    
    student_submission = None
    student_percentage = None
    score_released = False  # Score only shown after teacher explicitly reviews
    if is_student:
        student_submission = quiz.submissions.filter(student=request.user).order_by('-submitted_at').first()
        if student_submission:
            # Score is released when submission has been evaluated (auto-graded or teacher reviewed)
            score_released = student_submission.evaluated_at is not None or student_submission.evaluated_by is not None
            if score_released and student_submission.marks_obtained is not None and quiz.total_marks > 0:
                student_percentage = round((student_submission.marks_obtained / quiz.total_marks) * 100)
    
    total_question_marks = sum(q.marks for q in quiz.questions.all())
    
    return render(request, 'quizzes/quiz_detail.html', {
        'quiz': quiz,
        'classroom': classroom,
        'is_teacher': is_teacher,
        'is_student': is_student,
        'student_submission': student_submission,
        'student_percentage': student_percentage,
        'total_question_marks': total_question_marks,
        'total_students_count': total_students_count,
        'submitted_count': submitted_count,
        'graded_count': graded_count,
        'pending_grade_count': pending_grade_count,
        'missing_count': missing_count,
        'average_score': average_score,
        'submission_rate': submission_rate,
        'score_released': score_released,
    })


@login_required
def add_question(request, quiz_id):
    """Add a question to a quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher' or quiz.created_by != request.user:
        messages.error(request, 'Only the quiz creator can add questions')
        return JsonResponse({'success': False}, status=403)
    
    if request.method == 'POST':
        question_type = request.POST.get('question_type')
        question_text = (request.POST.get('question_text') or '').strip()
        marks = int(request.POST.get('marks', 1))
        order = quiz.questions.count()
        
        question = Question.objects.create(
            quiz=quiz,
            question_type=question_type,
            question_text=question_text,
            marks=marks,
            order=order
        )
        
        if question_type == 'mcq':
            choices = request.POST.getlist('choices[]')
            correct_choice = int(request.POST.get('correct_choice', 0))
            
            for i, choice_text in enumerate(choices):
                if choice_text.strip():
                    Choice.objects.create(
                        question=question,
                        choice_text=choice_text.strip(),
                        is_correct=(i == correct_choice),
                        order=i
                    )
        
        return JsonResponse({'success': True, 'question_id': question.id})
    
    return JsonResponse({'success': False}, status=400)


@login_required
def edit_question(request, question_id):
    """Get or update an existing question"""
    question = get_object_or_404(Question, id=question_id)
    quiz = question.quiz
    
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher' or quiz.created_by != request.user:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    if request.method == 'GET':
        choices_data = []
        for choice in question.choices.all():
            choices_data.append({
                'id': choice.id,
                'choice_text': choice.choice_text,
                'is_correct': choice.is_correct,
            })
        return JsonResponse({
            'success': True,
            'id': question.id,
            'question_type': question.question_type,
            'question_text': question.question_text,
            'marks': question.marks,
            'choices': choices_data
        })
        
    elif request.method == 'POST':
        question_type = request.POST.get('question_type', question.question_type)
        question_text = (request.POST.get('question_text') or '').strip()
        marks = int(request.POST.get('marks', question.marks))
        
        question.question_type = question_type
        question.question_text = question_text
        question.marks = marks
        question.save()
        
        if question_type == 'mcq':
            question.choices.all().delete()
            choices = request.POST.getlist('choices[]')
            correct_choice = int(request.POST.get('correct_choice', 0))
            for i, choice_text in enumerate(choices):
                if choice_text.strip():
                    Choice.objects.create(
                        question=question,
                        choice_text=choice_text.strip(),
                        is_correct=(i == correct_choice),
                        order=i
                    )
        elif question_type == 'text':
            question.choices.all().delete()
            
        return JsonResponse({'success': True, 'question_id': question.id})
        
    return JsonResponse({'success': False}, status=400)


@login_required
def delete_question(request, question_id):
    """Delete a question from a quiz"""
    question = get_object_or_404(Question, id=question_id)
    quiz = question.quiz
    
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher' or quiz.created_by != request.user:
        messages.error(request, 'Only the quiz creator can delete questions')
        return JsonResponse({'success': False}, status=403)
    
    question.delete()
    return JsonResponse({'success': True})


@login_required
def take_quiz(request, quiz_id):
    """Student takes a quiz — with server-side timer support."""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    classroom = quiz.classroom

    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'student':
        messages.error(request, 'Only students can take quizzes')
        return redirect('student_classrooms')

    if not classroom.memberships.filter(student=request.user, status='approved').exists():
        messages.error(request, 'You are not approved for this classroom')
        return redirect('student_classrooms')

    if quiz.status != 'published':
        messages.error(request, 'This quiz is private/draft and only available for live meeting use')
        return redirect('classroom_quizzes', classroom_id=classroom.id)

    if quiz.questions.count() == 0:
        messages.error(request, 'This quiz has no questions yet.')
        return redirect('classroom_quizzes', classroom_id=classroom.id)

    if quiz.due_date and timezone.now() > quiz.due_date:
        messages.error(request, 'This quiz time limit/due date has expired and is no longer available.')
        return redirect('classroom_quizzes', classroom_id=classroom.id)

    existing_submission = QuizSubmission.objects.filter(quiz=quiz, student=request.user).first()
    if existing_submission:
        messages.warning(request, 'You have already submitted this quiz')
        return redirect('quiz_detail', quiz_id=quiz_id)

    # ── Record when the student first opens the quiz ──────────────────────────
    session_key = f'quiz_{quiz_id}_started_at'
    if session_key not in request.session:
        request.session[session_key] = timezone.now().isoformat()

    try:
        started_at = timezone.datetime.fromisoformat(request.session[session_key])
    except Exception:
        started_at = timezone.now()
        request.session[session_key] = started_at.isoformat()

    if timezone.is_naive(started_at):
        started_at = timezone.make_aware(started_at)

    # ── How many seconds remain ───────────────────────────────────────────────
    seconds_remaining = None
    if quiz.time_limit:
        elapsed = int((timezone.now() - started_at).total_seconds())
        seconds_remaining = max(0, quiz.time_limit * 60 - elapsed)

    if request.method == 'POST':
        # Prevent double submission
        if QuizSubmission.objects.filter(quiz=quiz, student=request.user).exists():
            return redirect('quiz_detail', quiz_id=quiz_id)

        time_taken = int((timezone.now() - started_at).total_seconds())

        submission = QuizSubmission.objects.create(
            quiz=quiz,
            student=request.user,
            started_at=started_at,
            time_taken_seconds=time_taken,
        )

        questions = quiz.questions.all()
        for question in questions:
            if question.question_type == 'mcq':
                choice_id = request.POST.get(f'question_{question.id}')
                selected_choice = Choice.objects.filter(id=choice_id, question=question).first()
                StudentAnswer.objects.create(
                    submission=submission,
                    question=question,
                    selected_choice=selected_choice
                )
            elif question.question_type == 'text':
                text_answer = request.POST.get(f'question_{question.id}', '')
                StudentAnswer.objects.create(
                    submission=submission,
                    question=question,
                    text_answer=text_answer
                )

        # Auto-grade MCQ questions
        total = 0
        all_graded = True
        for answer in submission.answers.select_related('question', 'selected_choice'):
            if answer.question.question_type == 'mcq':
                pts = answer.question.marks if (answer.selected_choice and answer.selected_choice.is_correct) else 0
                answer.marks_obtained = pts
                total += pts
                answer.save()
            else:
                all_graded = False  # text answers need manual grading

        if all_graded:
            submission.marks_obtained = total
            submission.evaluated_at = timezone.now()
            submission.evaluated_by = None  # auto-graded
            submission.save()

        # Clean session key
        request.session.pop(session_key, None)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'ok', 'redirect': f'/assignments/quizzes/{quiz_id}/'})

        messages.success(request, 'Quiz submitted successfully!')
        return redirect('quiz_detail', quiz_id=quiz_id)

    return render(request, 'quizzes/take_quiz.html', {
        'quiz': quiz,
        'questions': quiz.questions.all(),
        'seconds_remaining': seconds_remaining,
        'started_at_iso': started_at.isoformat(),
    })


@login_required
def quiz_time_status(request, quiz_id):
    """JSON endpoint — returns seconds remaining for the timer."""
    quiz = get_object_or_404(Quiz, id=quiz_id)

    if not quiz.time_limit:
        return JsonResponse({'has_timer': False})

    session_key = f'quiz_{quiz_id}_started_at'
    started_str = request.session.get(session_key)
    if not started_str:
        return JsonResponse({'has_timer': False})

    try:
        started_at = timezone.datetime.fromisoformat(started_str)
    except Exception:
        return JsonResponse({'has_timer': False})

    if timezone.is_naive(started_at):
        started_at = timezone.make_aware(started_at)

    elapsed = int((timezone.now() - started_at).total_seconds())
    remaining = max(0, quiz.time_limit * 60 - elapsed)

    return JsonResponse({
        'has_timer': True,
        'seconds_remaining': remaining,
        'time_limit_seconds': quiz.time_limit * 60,
    })


@login_required
def evaluate_quiz_submission(request, submission_id):
    """Teacher evaluates a student's quiz submission"""
    submission = get_object_or_404(QuizSubmission, id=submission_id)
    quiz = submission.quiz
    classroom = quiz.classroom
    
    if not hasattr(request.user, 'userprofile') or request.user.userprofile.user_type != 'teacher' or classroom.teacher != request.user:
        messages.error(request, 'Only the classroom teacher can evaluate submissions')
        return redirect('teacher_classrooms')
    
    if request.method == 'POST':
        total_marks = 0
        answers = submission.answers.select_related('question').all()
        
        for answer in answers:
            marks = request.POST.get(f'marks_{answer.question.id}')
            if marks is not None and marks.strip() != '':
                try:
                    val = int(marks)
                except ValueError:
                    val = answer.marks_obtained or 0
                answer.marks_obtained = val
                total_marks += val
                answer.save()
            elif answer.marks_obtained is not None:
                total_marks += answer.marks_obtained
        
        feedback = request.POST.get('feedback', '')
        submission.marks_obtained = total_marks
        submission.feedback = feedback
        submission.evaluated_at = timezone.now()
        submission.evaluated_by = request.user
        submission.save()
        
        messages.success(request, 'Quiz evaluated successfully!')
        return redirect('quiz_detail', quiz_id=quiz.id)
    
    return render(request, 'quizzes/evaluate_quiz_submission.html', {
        'submission': submission,
        'quiz': quiz,
        'classroom': classroom,
        'answers': submission.answers.all()
    })


@login_required
def quiz_submissions(request, quiz_id):
    """Dedicated view for teacher to view and manage all student submissions and proctoring stats for a quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    classroom = quiz.classroom

    is_teacher = (
        hasattr(request.user, 'userprofile') and
        request.user.userprofile.user_type == 'teacher' and
        classroom.teacher == request.user
    )
    if not is_teacher:
        messages.error(request, 'Only classroom teachers can view all student submissions.')
        return redirect('quiz_detail', quiz_id=quiz.id)

    approved_students = [m.student for m in classroom.get_approved_memberships()]
    total_students_count = len(approved_students)
    submitted_count = 0
    graded_count = 0
    pending_grade_count = 0
    missing_count = 0
    submissions = []

    for student in approved_students:
        submission = quiz.submissions.filter(student=student).order_by('-submitted_at').first()
        if submission:
            submissions.append({
                'student': student,
                'submission': submission,
                'status': 'submitted'
            })
            submitted_count += 1
            if submission.marks_obtained is not None:
                graded_count += 1
            else:
                pending_grade_count += 1
        else:
            is_missing = quiz.due_date and timezone.now() > quiz.due_date
            if is_missing:
                missing_count += 1
            submissions.append({
                'student': student,
                'submission': None,
                'status': 'missing' if is_missing else 'pending'
            })

    graded_scores = [
        s['submission'].marks_obtained for s in submissions
        if s['submission'] and s['submission'].marks_obtained is not None
    ]
    average_score = None
    if graded_scores and quiz.total_marks > 0:
        average_score = round(sum(graded_scores) / len(graded_scores), 1)

    submission_rate = 0
    if total_students_count > 0:
        submission_rate = round((submitted_count / total_students_count) * 100)

    not_submitted_count = max(0, total_students_count - submitted_count)

    return render(request, 'quizzes/quiz_submissions.html', {
        'quiz': quiz,
        'classroom': classroom,
        'submissions': submissions,
        'total_students_count': total_students_count,
        'submitted_count': submitted_count,
        'graded_count': graded_count,
        'pending_grade_count': pending_grade_count,
        'missing_count': missing_count,
        'not_submitted_count': not_submitted_count,
        'average_score': average_score,
        'submission_rate': submission_rate,
    })

