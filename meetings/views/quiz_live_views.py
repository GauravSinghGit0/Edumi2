import json
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction

from meetings.models import Meeting
from assignments.models import Quiz, Question, Choice, QuizSubmission, StudentAnswer


@login_required
@require_http_methods(["GET"])
def get_available_classroom_quizzes(request, meeting_code):
    """
    Returns quizzes from the meeting's classroom available for the host to start.
    """
    meeting = get_object_or_404(Meeting, meeting_code=meeting_code)
    if meeting.teacher != request.user:
        return JsonResponse({'status': 'error', 'message': 'Only host can access classroom quizzes'}, status=403)

    if not meeting.classroom:
        return JsonResponse({'status': 'error', 'message': 'This meeting is not linked to a classroom'}, status=400)

    quizzes = meeting.classroom.quizzes.exclude(status='archived').prefetch_related('questions')
    quiz_data = []
    for q in quizzes:
        q_count = q.questions.count()
        quiz_data.append({
            'id': q.id,
            'title': q.title,
            'description': q.description or '',
            'total_marks': q.total_marks,
            'time_limit': q.time_limit,
            'status': q.status,
            'question_count': q_count,
            'created_at': q.created_at.strftime('%Y-%m-%d %H:%M')
        })

    return JsonResponse({
        'status': 'success',
        'classroom_title': meeting.classroom.title,
        'quizzes': quiz_data
    })


@login_required
@require_http_methods(["POST"])
def start_meeting_quiz(request, meeting_code):
    """
    Teacher selects and starts a classroom quiz in the live meeting.
    Returns sanitised quiz structure (without correct answer indications).
    """
    meeting = get_object_or_404(Meeting, meeting_code=meeting_code)
    if meeting.teacher != request.user:
        return JsonResponse({'status': 'error', 'message': 'Only the host can start a live quiz'}, status=403)

    try:
        data = json.loads(request.body)
        quiz_id = data.get('quiz_id')
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON body'}, status=400)

    quiz = get_object_or_404(Quiz, id=quiz_id)
    if meeting.classroom and quiz.classroom_id != meeting.classroom_id:
        return JsonResponse({'status': 'error', 'message': 'Quiz does not belong to this meeting classroom'}, status=400)

    if quiz.status == 'archived':
        return JsonResponse({'status': 'error', 'message': 'Cannot launch an archived quiz'}, status=400)

    if quiz.questions.count() == 0:
        return JsonResponse({'status': 'error', 'message': 'Cannot launch a quiz with no questions. Please add questions in the Classroom first.'}, status=400)

    questions = quiz.questions.all().order_by('order', 'id').prefetch_related('choices')
    questions_payload = []
    for q in questions:
        choices_payload = []
        if q.question_type == 'mcq':
            for c in q.choices.all().order_by('order', 'id'):
                choices_payload.append({
                    'id': c.id,
                    'choice_text': c.choice_text
                })

        questions_payload.append({
            'id': q.id,
            'question_type': q.question_type,
            'question_text': q.question_text,
            'marks': q.marks,
            'choices': choices_payload
        })

    quiz_payload = {
        'id': quiz.id,
        'title': quiz.title,
        'description': quiz.description or '',
        'total_marks': quiz.total_marks,
        'time_limit': quiz.time_limit,
        'questions': questions_payload
    }

    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'meeting_{meeting_code.upper()}',
                {
                    'type': 'quiz_started',
                    'quiz': quiz_payload,
                    'host_name': request.user.get_full_name() or request.user.username
                }
            )
    except Exception as e:
        pass

    return JsonResponse({
        'status': 'success',
        'quiz': quiz_payload
    })


@login_required
@require_http_methods(["POST"])
def submit_meeting_quiz(request, meeting_code):
    """
    Submits a student's live meeting quiz answers, auto-grades MCQ questions, and logs anti-cheating tab switch violations.
    """
    meeting = get_object_or_404(Meeting, meeting_code=meeting_code)
    try:
        data = json.loads(request.body)
        quiz_id = data.get('quiz_id')
        answers_dict = data.get('answers', {})
        time_taken_seconds = data.get('time_taken_seconds', 0)
        tab_switch_count = int(data.get('tab_switch_count', 0))
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Invalid data: {str(e)}'}, status=400)

    quiz = get_object_or_404(Quiz, id=quiz_id)

    with transaction.atomic():
        submission, created = QuizSubmission.objects.get_or_create(
            quiz=quiz,
            student=request.user,
            meeting=meeting,
            defaults={
                'is_live_meeting_quiz': True,
                'started_at': timezone.now(),
                'tab_switch_count': tab_switch_count,
                'time_taken_seconds': time_taken_seconds
            }
        )

        submission.tab_switch_count = tab_switch_count
        submission.time_taken_seconds = time_taken_seconds
        submission.submitted_at = timezone.now()

        total_obtained_marks = 0
        questions = {q.id: q for q in quiz.questions.prefetch_related('choices').all()}

        for q_id_str, ans_data in answers_dict.items():
            try:
                q_id = int(q_id_str)
            except ValueError:
                continue

            question = questions.get(q_id)
            if not question:
                continue

            selected_choice_id = ans_data.get('selected_choice')
            text_answer = ans_data.get('text_answer', '').strip()

            selected_choice = None
            marks_for_q = 0

            if question.question_type == 'mcq' and selected_choice_id:
                try:
                    selected_choice = Choice.objects.get(id=int(selected_choice_id), question=question)
                    if selected_choice.is_correct:
                        marks_for_q = question.marks
                except (Choice.DoesNotExist, ValueError):
                    selected_choice = None

            StudentAnswer.objects.update_or_create(
                submission=submission,
                question=question,
                defaults={
                    'selected_choice': selected_choice,
                    'text_answer': text_answer,
                    'marks_obtained': marks_for_q if question.question_type == 'mcq' else None
                }
            )

            if question.question_type == 'mcq':
                total_obtained_marks += marks_for_q

        submission.marks_obtained = total_obtained_marks
        has_text_questions = any(q.question_type == 'text' for q in questions.values())
        if not has_text_questions:
            submission.evaluated_at = timezone.now()
        submission.save()

    is_auto_submitted = data.get('is_auto_submitted', False)

    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'meeting_{meeting_code.upper()}',
                {
                    'type': 'quiz_submitted',
                    'student_id': request.user.id,
                    'student_name': request.user.get_full_name() or request.user.username,
                    'quiz_id': quiz.id,
                    'tab_switch_count': tab_switch_count,
                    'is_auto_submitted': is_auto_submitted,
                    'marks_obtained': submission.marks_obtained,
                    'total_marks': quiz.total_marks
                }
            )
    except Exception as e:
        pass

    return JsonResponse({
        'status': 'success',
        'message': 'Quiz submitted successfully!',
        'marks_obtained': submission.marks_obtained,
        'total_marks': quiz.total_marks
    })


@login_required
@require_http_methods(["GET"])
def get_meeting_quiz_submissions(request, meeting_id, quiz_id):
    """
    Classroom Teacher view: Fetches all student submissions for a specific meeting quiz session.
    """
    meeting = get_object_or_404(Meeting, id=meeting_id)
    quiz = get_object_or_404(Quiz, id=quiz_id)

    if meeting.teacher != request.user and quiz.created_by != request.user:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)

    submissions = QuizSubmission.objects.filter(
        meeting=meeting, quiz=quiz
    ).select_related('student').prefetch_related('answers__question', 'answers__selected_choice')

    student_results = []
    for sub in submissions:
        ans_list = []
        for ans in sub.answers.all():
            correct_choice = ans.question.choices.filter(is_correct=True).first() if ans.question.question_type == 'mcq' else None
            ans_list.append({
                'question_id': ans.question.id,
                'question_text': ans.question.question_text,
                'question_type': ans.question.question_type,
                'marks': ans.question.marks,
                'selected_choice_id': ans.selected_choice.id if ans.selected_choice else None,
                'selected_choice_text': ans.selected_choice.choice_text if ans.selected_choice else 'Skipped',
                'correct_choice_text': correct_choice.choice_text if correct_choice else None,
                'text_answer': ans.text_answer or '',
                'marks_obtained': ans.marks_obtained
            })

        student_results.append({
            'submission_id': sub.id,
            'student_id': sub.student.id,
            'student_name': sub.student.get_full_name() or sub.student.username,
            'student_username': sub.student.username,
            'submitted_at': sub.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if sub.submitted_at else '',
            'time_taken_display': sub.time_taken_display,
            'tab_switch_count': sub.tab_switch_count,
            'marks_obtained': sub.marks_obtained,
            'total_marks': quiz.total_marks,
            'feedback': sub.feedback or '',
            'answers': ans_list
        })

    return JsonResponse({
        'status': 'success',
        'quiz_title': quiz.title,
        'meeting_title': meeting.title,
        'submissions': student_results
    })
