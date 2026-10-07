"""
rag_workspace/views.py
Views for the dedicated AI Study Workspace application & RAG API endpoints.
"""

import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

from meetings.models import Classroom, StudyMaterial, MaterialUnit, ClassroomMembership
from .models import RagSession, RagQueryLog, RagInstructorSetting
from .services import run_rag_workspace_pipeline, run_rag_workspace_pipeline_stream


def check_classroom_access(classroom, user):
    """Returns (has_access, is_teacher) tuple for a given classroom and user."""
    if not user or not user.is_authenticated:
        return False, False
    is_teacher = (classroom.teacher_id == user.id)
    if is_teacher:
        return True, True
    is_approved_student = ClassroomMembership.objects.filter(
        classroom=classroom,
        student=user,
        status='approved'
    ).exists()
    return is_approved_student, False


@login_required
def rag_workspace_view(request):
    """
    Dedicated AI Study Workspace Application View.
    Renders standalone AI Study Assistant with selection panel, mode canvas, and citations.
    """
    user = request.user
    
    if hasattr(user, 'userprofile') and user.userprofile.user_type == 'teacher':
        classrooms = Classroom.objects.filter(teacher=user, is_active=True)
        is_teacher = True
    else:
        classrooms = Classroom.objects.filter(
            memberships__student=user,
            memberships__status='approved',
            is_active=True
        )
        is_teacher = False

    classroom_filter = request.GET.get('classroom', '').strip()
    selected_material_ids_raw = request.GET.get('materials', '').strip()

    materials = StudyMaterial.objects.filter(
        classroom__in=classrooms,
        is_published=True
    ).select_related('classroom', 'unit').order_by('-created_at')

    if classroom_filter and classroom_filter.isdigit():
        materials = materials.filter(classroom_id=int(classroom_filter))

    # Pre-selected material IDs from query string
    initial_selected_ids = []
    if selected_material_ids_raw:
        try:
            initial_selected_ids = [int(x) for x in selected_material_ids_raw.split(',') if x.strip().isdigit()]
        except Exception:
            pass

    return render(request, 'rag_workspace/workspace.html', {
        'classrooms': classrooms,
        'materials': materials,
        'is_teacher': is_teacher,
        'current_classroom': classroom_filter,
        'initial_selected_ids': initial_selected_ids,
        'total_materials_count': materials.count(),
    })


@login_required
@require_http_methods(["GET"])
def rag_materials_api(request):
    """
    GET API returning accessible study materials formatted with selection metadata,
    RAG readiness status, page count, and classroom details.
    """
    user = request.user
    classroom_id = request.GET.get('classroom_id')

    if hasattr(user, 'userprofile') and user.userprofile.user_type == 'teacher':
        classrooms = Classroom.objects.filter(teacher=user, is_active=True)
    else:
        classrooms = Classroom.objects.filter(
            memberships__student=user,
            memberships__status='approved',
            is_active=True
        )

    if classroom_id and classroom_id.isdigit():
        classrooms = classrooms.filter(id=int(classroom_id))

    materials = StudyMaterial.objects.filter(
        classroom__in=classrooms,
        is_published=True
    ).select_related('classroom', 'unit').order_by('-created_at')

    items = []
    for m in materials:
        chunks_count = m.chunks.count()
        pages_count = max(1, chunks_count)

        items.append({
            'id': m.id,
            'title': m.title,
            'description': m.description or '',
            'material_type': m.material_type,
            'material_type_display': m.get_material_type_display(),
            'file_name': m.file.name.split('/')[-1] if m.file else (m.title + '.pdf'),
            'file_size': m.get_file_size_formatted() or 'N/A',
            'file_url': m.file.url if m.file else None,
            'pages_count': pages_count,
            'chunks_count': chunks_count,
            'rag_indexed': m.rag_indexed,
            'rag_status': 'RAG Ready' if m.rag_indexed else 'Processing',
            'rag_status_code': 'ready' if m.rag_indexed else 'processing',
            'unit_id': m.unit_id,
            'unit_title': m.unit.title if m.unit else 'General',
            'classroom_id': m.classroom_id,
            'classroom_title': m.classroom.title,
            'icon_name': m.get_icon_name(),
            'badge_color': m.get_badge_color(),
            'created_at': m.created_at.strftime('%b %d, %Y')
        })

    return JsonResponse({
        'status': 'success',
        'count': len(items),
        'materials': items
    })


@login_required
@csrf_protect
@require_http_methods(["POST"])
def rag_chat_api(request):
    """
    POST API for AI Study Workspace. Runs grounded RAG queries across selected materials.

    Supports two transport modes based on the `stream` field:
      - stream=false (default): single JsonResponse with full answer + sources. Safe default.
      - stream=true:           StreamingHttpResponse emitting newline-delimited JSON chunks
                               `data: {...}\n\n` so Cloudflare Quick Tunnel sees continuous bytes
                               and does not kill the connection on idle timeout.
    """
    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    material_ids = data.get('material_ids', [])
    if isinstance(material_ids, str):
        try:
            material_ids = json.loads(material_ids)
        except Exception:
            material_ids = [int(x) for x in material_ids.split(',') if x.strip().isdigit()]

    material_ids = [int(m) for m in material_ids if str(m).isdigit()]

    if not material_ids:
        err_payload = {
            'status': 'error',
            'message': 'No study materials selected. Please select at least one resource.',
            'not_found': True,
            'answer': 'Please select at least one study resource to start an AI study session.'
        }
        stream_flag = str(data.get('stream', '')).lower() in ('1', 'true', 'yes')
        if stream_flag:
            def _empty_err():
                yield ('data: ' + json.dumps({'type': 'error', **err_payload}) + '\n\n')
                yield ('data: ' + json.dumps({'type': 'done', **err_payload}) + '\n\n')
            return StreamingHttpResponse(_empty_err(), content_type='text/event-stream')
        return JsonResponse(err_payload, status=400)

    prompt = data.get('prompt', '').strip()
    mode = data.get('mode', 'ask').lower()
    explain_level = data.get('explain_level', 'detailed').lower()
    strict_mode = bool(data.get('strict_mode', True))
    allow_external = bool(data.get('allow_external', False))
    session_id = data.get('session_id')
    stream_flag = str(data.get('stream', '')).lower() in ('1', 'true', 'yes')

    if stream_flag:
        def _iter_stream_frames():
            for frame in run_rag_workspace_pipeline_stream(
                user=request.user,
                material_ids=material_ids,
                prompt=prompt,
                mode=mode,
                explain_level=explain_level,
                strict_mode=strict_mode,
                allow_external=allow_external,
                session_id=session_id,
            ):
                yield 'data: ' + json.dumps(frame, ensure_ascii=False) + '\n\n'
            yield 'data: ' + json.dumps({'type': 'eos'}) + '\n\n'

        response = StreamingHttpResponse(_iter_stream_frames(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache, no-transform'
        response['X-Accel-Buffering'] = 'no'
        response['Connection'] = 'keep-alive'
        return response

    result = run_rag_workspace_pipeline(
        user=request.user,
        material_ids=material_ids,
        prompt=prompt,
        mode=mode,
        explain_level=explain_level,
        strict_mode=strict_mode,
        allow_external=allow_external,
        session_id=session_id
    )
    return JsonResponse(result)


@login_required
@csrf_protect
@require_http_methods(["GET", "POST"])
def rag_instructor_settings_api(request):
    """
    GET/POST endpoint for instructor AI control settings per course.
    """
    if request.method == "GET":
        classroom_id = request.GET.get('classroom_id')
        if classroom_id and classroom_id.isdigit():
            setting = RagInstructorSetting.objects.filter(classroom_id=int(classroom_id)).first()
            if setting:
                return JsonResponse({
                    'status': 'success',
                    'settings': {
                        'allow_questions': setting.allow_questions,
                        'allow_summaries': setting.allow_summaries,
                        'allow_quiz': setting.allow_quiz,
                        'allow_revision': setting.allow_revision,
                        'show_citations': setting.show_citations,
                        'allow_change_scope': setting.allow_change_scope,
                        'allow_outside_knowledge': setting.allow_outside_knowledge,
                        'strict_material_mode': setting.strict_material_mode,
                    }
                })

        settings_dict = request.session.get('instructor_ai_settings', {
            'allow_questions': True,
            'allow_summaries': True,
            'allow_quiz': True,
            'allow_revision': True,
            'show_citations': True,
            'allow_change_scope': True,
            'allow_outside_knowledge': False,
            'strict_material_mode': True,
        })
        return JsonResponse({'status': 'success', 'settings': settings_dict})

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        classroom_id = data.get('classroom_id')
        if classroom_id and str(classroom_id).isdigit():
            cr = get_object_or_404(Classroom, id=int(classroom_id))
            has_access, is_teacher = check_classroom_access(cr, request.user)
            if not is_teacher:
                return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

            setting, _ = RagInstructorSetting.objects.get_or_create(classroom=cr)
            setting.allow_questions = bool(data.get('allow_questions', True))
            setting.allow_summaries = bool(data.get('allow_summaries', True))
            setting.allow_quiz = bool(data.get('allow_quiz', True))
            setting.allow_revision = bool(data.get('allow_revision', True))
            setting.show_citations = bool(data.get('show_citations', True))
            setting.allow_change_scope = bool(data.get('allow_change_scope', True))
            setting.allow_outside_knowledge = bool(data.get('allow_outside_knowledge', False))
            setting.strict_material_mode = bool(data.get('strict_material_mode', True))
            setting.save()

        current_settings = request.session.get('instructor_ai_settings', {})
        for k in ['allow_questions', 'allow_summaries', 'allow_quiz', 'allow_revision', 'show_citations', 'allow_change_scope', 'allow_outside_knowledge', 'strict_material_mode']:
            if k in data:
                current_settings[k] = bool(data[k])
        request.session['instructor_ai_settings'] = current_settings

        return JsonResponse({'status': 'success', 'message': 'Instructor controls saved successfully.'})


@login_required
@csrf_protect
@require_http_methods(["GET", "POST", "DELETE"])
def rag_sessions_api(request):
    """
    API for managing user AI chat sessions (ChatGPT style history).
    GET: List user's sessions.
    POST: Create a new session.
    DELETE: Delete a session by ID.
    """
    user = request.user

    if request.method == "GET":
        sessions = RagSession.objects.filter(user=user).order_by('-updated_at')[:40]
        data = [{
            'id': s.id,
            'title': s.title,
            'active_mode': s.active_mode,
            'updated_at': s.updated_at.strftime('%b %d, %H:%M'),
            'created_at': s.created_at.strftime('%b %d, %Y'),
            'materials_count': s.selected_materials.count(),
            'messages_count': s.messages.count(),
        } for s in sessions]
        return JsonResponse({'status': 'success', 'sessions': data})

    elif request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            body = request.POST

        title = body.get('title', 'New AI Study Session').strip() or 'New AI Study Session'
        session = RagSession.objects.create(
            user=user,
            title=title,
            active_mode=body.get('mode', 'ask')
        )
        return JsonResponse({
            'status': 'success',
            'session': {
                'id': session.id,
                'title': session.title,
                'updated_at': session.updated_at.strftime('%b %d, %H:%M')
            }
        })

    elif request.method == "DELETE":
        session_id = request.GET.get('id') or request.POST.get('id')
        if not session_id and request.body:
            try:
                body = json.loads(request.body)
                session_id = body.get('id')
            except Exception:
                pass

        if session_id and str(session_id).isdigit():
            RagSession.objects.filter(id=int(session_id), user=user).delete()
            return JsonResponse({'status': 'success', 'message': 'Session deleted.'})
        return JsonResponse({'status': 'error', 'message': 'Invalid session ID.'}, status=400)


@login_required
@require_http_methods(["GET"])
def rag_session_detail_api(request, session_id):
    """
    GET API returning messages inside a specific user session.
    """
    session = get_object_or_404(RagSession, id=session_id, user=request.user)
    messages = session.messages.order_by('created_at')
    
    msg_data = [{
        'id': m.id,
        'role': m.role,
        'content': m.content,
        'sources': m.sources or [],
        'created_at': m.created_at.strftime('%H:%M')
    } for m in messages]

    selected_ids = list(session.selected_materials.values_list('id', flat=True))

    return JsonResponse({
        'status': 'success',
        'session': {
            'id': session.id,
            'title': session.title,
            'active_mode': session.active_mode,
            'selected_ids': selected_ids
        },
        'messages': msg_data
    })

