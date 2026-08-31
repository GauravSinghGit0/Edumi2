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
    
    if is_teacher:
        quizzes = classroom.quizzes.all()
    else:
        # Students only see published quizzes whose due_date has not passed
        now = timezone.now()
        quizzes = classroom.quizzes.filter(status='published').filter(
            models.Q(due_date__gte=now) | models.Q(due_date__isnull=True)
        )
    
    return render(request, 'quizzes/classroom_quizzes.html', {
        'classroom': classroom,
        'quizzes': quizzes,
        'is_teacher': is_teacher
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
        
        quiz = Quiz.objects.create(
            classroom=classroom,
            title=title,
            description=description,
            total_marks=total_marks,
            time_limit=time_limit,
            due_date=due_date,
            created_by=request.user
        )
        
        if request.POST.get('action') == 'publish':
            quiz.status = 'published'
            quiz.save()
            messages.success(request, f'Quiz "{title}" published successfully!')
        else:
            messages.success(request, f'Quiz "{title}" saved as draft!')
        
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
            quiz.status = 'published'
        elif action == 'archive':
            quiz.status = 'archived'
        # For 'save' action, we just keep the current status
        
        quiz.save()
        messages.success(request, f'Quiz "{quiz.title}" updated successfully!')
        return redirect('edit_quiz', quiz_id=quiz.id)
    
    return render(request, 'quizzes/edit_quiz.html', {
        'quiz': quiz
    })


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
    
    submissions = []
    if is_teacher:
        approved_students = [m.student for m in classroom.get_approved_memberships()]
        for student in approved_students:
            try:
                submission = quiz.submissions.get(student=student)
                submissions.append({
                    'student': student,
                    'submission': submission,
                    'status': 'submitted'
                })
            except QuizSubmission.DoesNotExist:
                submissions.append({
                    'student': student,
                    'submission': None,
                    'status': 'missing' if quiz.due_date and timezone.now() > quiz.due_date else 'pending'
                })
    
    student_submission = None
    if is_student:
        try:
            student_submission = quiz.submissions.get(student=request.user)
        except QuizSubmission.DoesNotExist:
            pass
    
    return render(request, 'quizzes/quiz_detail.html', {
        'quiz': quiz,
        'classroom': classroom,
        'is_teacher': is_teacher,
        'is_student': is_student,
        'submissions': submissions,
        'student_submission': student_submission
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

    started_at = timezone.datetime.fromisoformat(request.session[session_key])
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

    started_at = timezone.datetime.fromisoformat(started_str)
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
        answers = submission.answers.all()
        
        for answer in answers:
            marks = request.POST.get(f'marks_{answer.question.id}')
            if marks:
                answer.marks_obtained = int(marks)
                total_marks += int(marks)
                answer.save()
        
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
