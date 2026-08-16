"""
meetings/views/material_views.py
Views for Study Materials, Digital Library, Unit organization, and RAG indexing.
"""
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db.models import Q, F
from django.utils import timezone

from meetings.models import Classroom, ClassroomMembership, MaterialUnit, StudyMaterial, MaterialChunk, MaterialBookmark


def check_classroom_access(classroom, user):
    """Returns (has_access, is_teacher) tuple for a given classroom and user."""
    if not user.is_authenticated:
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


def auto_chunk_and_index_rag(material):
    """
    RAG Pre-processor:
    Extracts text, creates text chunks with token estimates, generates key topics, and marks RAG readiness.
    """
    raw_text = material.content_text or material.description or ""
    
    # If a file is uploaded, attempt to read plaintext or describe metadata
    if material.file and not raw_text:
        ext = (material.file_extension or '').lower()
        if ext in ['txt', 'md', 'py', 'json', 'csv', 'html']:
            try:
                material.file.open('r')
                raw_text = material.file.read()[:50000] # Cap initial read
                material.file.close()
            except Exception:
                pass

    if not raw_text:
        raw_text = f"{material.title}\n\n{material.description}"

    material.extracted_text = raw_text

    # Extract keywords/topics for hybrid search
    words = [w.strip('.,()[]:;"\'') for w in raw_text.split() if len(w) > 4]
    unique_topics = list(dict.fromkeys([w.capitalize() for w in words[:25]]))
    material.key_topics = unique_topics[:8]

    # Create summary
    first_paragraph = raw_text.strip().split('\n\n')[0] if raw_text else material.title
    material.summary_ai = (first_paragraph[:280] + '...') if len(first_paragraph) > 280 else first_paragraph

    # Chunk the text (e.g. ~400 characters / ~80 tokens per chunk)
    chunk_size = 400
    paragraphs = [raw_text[i:i+chunk_size] for i in range(0, len(raw_text), chunk_size)] if raw_text else [material.title]

    # Clear old chunks if any
    material.chunks.all().delete()

    for idx, p_text in enumerate(paragraphs):
        approx_tokens = len(p_text.split())
        MaterialChunk.objects.create(
            material=material,
            chunk_index=idx,
            chunk_text=p_text,
            token_count=approx_tokens,
            embedding_id=f"emb_mat_{material.id}_chunk_{idx}",
            metadata={
                'source': material.title,
                'type': material.material_type,
                'classroom_id': material.classroom_id,
                'chunk_idx': idx,
            }
        )

    material.rag_indexed = True
    material.rag_indexed_at = timezone.now()
    material.rag_metadata = {
        'total_chunks': len(paragraphs),
        'vector_collection': f"classroom_{material.classroom_id}_library",
        'embedding_model': 'text-embedding-3-small (Simulated Ready)',
    }
    material.save(update_fields=['extracted_text', 'summary_ai', 'key_topics', 'rag_indexed', 'rag_indexed_at', 'rag_metadata'])


@login_required
def classroom_materials_view(request, classroom_id):
    """Classroom specific Study Materials & Digital Library Hub."""
    classroom = get_object_or_404(Classroom, id=classroom_id)
    has_access, is_teacher = check_classroom_access(classroom, request.user)
    if not has_access:
        messages.error(request, 'You do not have access to this classroom library.')
        return redirect('student_classrooms')

    units = classroom.material_units.all().prefetch_related('materials')
    all_materials = classroom.study_materials.filter(is_published=True).select_related('unit', 'uploaded_by')

    # Filtering
    mat_type = request.GET.get('type', '').strip()
    query = request.GET.get('q', '').strip()
    unit_filter = request.GET.get('unit', '').strip()

    if mat_type:
        all_materials = all_materials.filter(material_type=mat_type)
    if query:
        all_materials = all_materials.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(content_text__icontains=query) |
            Q(extracted_text__icontains=query)
        )
    if unit_filter:
        if unit_filter == 'none':
            all_materials = all_materials.filter(unit__isnull=True)
        else:
            all_materials = all_materials.filter(unit_id=unit_filter)

    # Annotate bookmarks for current user
    bookmarked_ids = set(MaterialBookmark.objects.filter(user=request.user, material__in=all_materials).values_list('material_id', flat=True))
    for m in all_materials:
        m.is_bookmarked = m.id in bookmarked_ids

    return render(request, 'meetings/classroom/classroom_materials.html', {
        'classroom': classroom,
        'is_teacher': is_teacher,
        'units': units,
        'materials': all_materials,
        'current_type': mat_type,
        'current_query': query,
        'current_unit': unit_filter,
        'total_materials_count': classroom.study_materials.count(),
    })


@login_required
@require_http_methods(["POST"])
def upload_study_material(request, classroom_id):
    """Upload a new study material (Document, Video, Slides, Link, Notes)."""
    classroom = get_object_or_404(Classroom, id=classroom_id)
    has_access, is_teacher = check_classroom_access(classroom, request.user)
    if not is_teacher:
        return JsonResponse({'status': 'error', 'message': 'Only instructors can upload study materials.'}, status=403)

    title = request.POST.get('title', '').strip()
    if not title:
        return JsonResponse({'status': 'error', 'message': 'Title is required.'}, status=400)

    description = request.POST.get('description', '').strip()
    material_type = request.POST.get('material_type', 'document')
    unit_id = request.POST.get('unit_id')
    external_url = request.POST.get('external_url', '').strip()
    content_text = request.POST.get('content_text', '').strip()
    uploaded_file = request.FILES.get('file')

    unit = None
    if unit_id and unit_id.isdigit():
        unit = MaterialUnit.objects.filter(id=int(unit_id), classroom=classroom).first()

    # Determine file size and extension
    file_size = 0
    file_ext = ''
    if uploaded_file:
        file_size = uploaded_file.size
        file_ext = os.path.splitext(uploaded_file.name)[1].lstrip('.').lower()
        
        # Auto-detect material type if not explicitly set
        if file_ext in ['pdf', 'doc', 'docx', 'txt', 'rtf', 'odt']:
            material_type = 'document'
        elif file_ext in ['ppt', 'pptx', 'key']:
            material_type = 'slides'
        elif file_ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']:
            material_type = 'video'
        elif file_ext in ['epub', 'mobi']:
            material_type = 'book'

    material = StudyMaterial.objects.create(
        classroom=classroom,
        unit=unit,
        title=title,
        description=description,
        material_type=material_type,
        file=uploaded_file,
        external_url=external_url or None,
        content_text=content_text,
        file_size_bytes=file_size,
        file_extension=file_ext,
        uploaded_by=request.user,
        is_published=True,
    )

    # Trigger automatic RAG chunking & embedding readiness pipeline
    auto_chunk_and_index_rag(material)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'message': 'Study material uploaded and indexed for AI search successfully!',
            'material_id': material.id,
            'title': material.title,
            'description': material.description or '',
            'material_type': material.material_type,
            'badge_color': material.get_badge_color(),
            'icon_name': material.get_icon_name(),
            'file_url': material.file.url if material.file else None,
            'download_url': f"/meetings/materials/{material.id}/download/" if material.file else None,
            'external_url': material.external_url or '',
            'unit_id': unit.id if unit else None,
            'unit_title': unit.title if unit else 'General',
            'file_size': material.get_file_size_formatted(),
            'chunks_count': material.chunks.count(),
            'rag_indexed': material.rag_indexed,
            'is_teacher': is_teacher,
        })

    messages.success(request, f'Material "{title}" added to library!')
    return redirect('classroom_materials', classroom_id=classroom.id)


@login_required
@require_http_methods(["POST"])
def create_material_unit(request, classroom_id):
    """Create a new curriculum unit or topic folder."""
    classroom = get_object_or_404(Classroom, id=classroom_id)
    has_access, is_teacher = check_classroom_access(classroom, request.user)
    if not is_teacher:
        return JsonResponse({'status': 'error', 'message': 'Only instructors can create units.'}, status=403)

    title = request.POST.get('title', '').strip()
    if not title:
        return JsonResponse({'status': 'error', 'message': 'Unit title is required.'}, status=400)

    description = request.POST.get('description', '').strip()
    next_order = classroom.material_units.count() + 1

    unit = MaterialUnit.objects.create(
        classroom=classroom,
        title=title,
        description=description,
        order=next_order
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'unit_id': unit.id,
            'title': unit.title,
            'description': unit.description,
        })

    messages.success(request, f'Unit "{title}" created successfully!')
    return redirect('classroom_materials', classroom_id=classroom.id)


@login_required
@require_http_methods(["POST"])
def delete_study_material(request, material_id):
    """Delete a study material."""
    material = get_object_or_404(StudyMaterial, id=material_id)
    has_access, is_teacher = check_classroom_access(material.classroom, request.user)
    if not is_teacher:
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    classroom_id = material.classroom_id
    title = material.title
    material.delete()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'message': f'Material "{title}" deleted.'})

    messages.success(request, f'Material "{title}" deleted successfully.')
    return redirect('classroom_materials', classroom_id=classroom_id)


@login_required
@require_http_methods(["POST"])
def toggle_material_bookmark(request, material_id):
    """Toggle bookmark on a study material."""
    material = get_object_or_404(StudyMaterial, id=material_id)
    has_access, _ = check_classroom_access(material.classroom, request.user)
    if not has_access:
        return JsonResponse({'status': 'error', 'message': 'Access denied.'}, status=403)

    bookmark = MaterialBookmark.objects.filter(material=material, user=request.user).first()
    if bookmark:
        bookmark.delete()
        is_bookmarked = False
    else:
        MaterialBookmark.objects.create(material=material, user=request.user)
        is_bookmarked = True

    return JsonResponse({'status': 'success', 'is_bookmarked': is_bookmarked})


@login_required
def download_study_material(request, material_id):
    """Download study material file with counter tracking."""
    material = get_object_or_404(StudyMaterial, id=material_id)
    has_access, _ = check_classroom_access(material.classroom, request.user)
    if not has_access:
        raise Http404("Access denied")

    if not material.file:
        if material.external_url:
            return redirect(material.external_url)
        raise Http404("No file attached to this material")

    # Increment download count
    StudyMaterial.objects.filter(id=material.id).update(download_count=F('download_count') + 1)

    filename = os.path.basename(material.file.name)
    response = FileResponse(material.file.open('rb'), as_attachment=True, filename=filename)
    return response


@login_required
def material_detail_api(request, material_id):
    """Returns JSON detail of material including RAG chunks, AI summary, and media stream preview."""
    material = get_object_or_404(StudyMaterial, id=material_id)
    has_access, is_teacher = check_classroom_access(material.classroom, request.user)
    if not has_access:
        return JsonResponse({'status': 'error', 'message': 'Access denied'}, status=403)

    # Increment view count
    StudyMaterial.objects.filter(id=material.id).update(view_count=F('view_count') + 1)

    chunks_data = [{
        'index': c.chunk_index,
        'text': c.chunk_text,
        'token_count': c.token_count,
        'embedding_id': c.embedding_id,
    } for c in material.chunks.all()]

    is_video = bool(material.material_type == 'video' or material.file_extension in ['mp4', 'webm', 'mov', 'mkv', 'avi'])
    is_pdf = bool(material.file_extension == 'pdf' or material.material_type == 'book')

    return JsonResponse({
        'status': 'success',
        'id': material.id,
        'title': material.title,
        'description': material.description,
        'material_type': material.material_type,
        'material_type_display': material.get_material_type_display(),
        'file_url': material.file.url if material.file else None,
        'file_size': material.get_file_size_formatted(),
        'external_url': material.external_url,
        'content_text': material.content_text,
        'summary_ai': material.summary_ai,
        'key_topics': material.key_topics,
        'rag_indexed': material.rag_indexed,
        'rag_metadata': material.rag_metadata,
        'chunks_count': len(chunks_data),
        'chunks': chunks_data,
        'views': material.view_count + 1,
        'downloads': material.download_count,
        'uploaded_by': material.uploaded_by.get_full_name() or material.uploaded_by.username,
        'created_at': material.created_at.strftime('%b %d, %Y'),
        'is_video': is_video,
        'is_pdf': is_pdf,
        'stream_url': material.file.url if material.file else (material.external_url if is_video else None),
    })


@login_required
def digital_library_view(request):
    """Global Digital Library across all user's accessible classrooms with cross-subject search."""
    if hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'teacher':
        classrooms = Classroom.objects.filter(teacher=request.user, is_active=True)
    else:
        classrooms = Classroom.objects.filter(
            memberships__student=request.user,
            memberships__status='approved',
            is_active=True
        )

    materials = StudyMaterial.objects.filter(
        classroom__in=classrooms,
        is_published=True
    ).select_related('classroom', 'unit', 'uploaded_by').order_by('-created_at')

    # Global search & filters
    query = request.GET.get('q', '').strip()
    mat_type = request.GET.get('type', '').strip()
    classroom_filter = request.GET.get('classroom', '').strip()
    bookmarks_only = request.GET.get('bookmarked', '') == 'true'

    if query:
        materials = materials.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(extracted_text__icontains=query) |
            Q(classroom__title__icontains=query)
        )
    if mat_type:
        materials = materials.filter(material_type=mat_type)
    if classroom_filter and classroom_filter.isdigit():
        materials = materials.filter(classroom_id=int(classroom_filter))
    if bookmarks_only:
        materials = materials.filter(bookmarks__user=request.user)

    bookmarked_ids = set(MaterialBookmark.objects.filter(user=request.user, material__in=materials).values_list('material_id', flat=True))
    for m in materials:
        m.is_bookmarked = m.id in bookmarked_ids

    return render(request, 'meetings/classroom/digital_library.html', {
        'classrooms': classrooms,
        'materials': materials,
        'current_query': query,
        'current_type': mat_type,
        'current_classroom': classroom_filter,
        'bookmarks_only': bookmarks_only,
        'total_count': materials.count(),
    })
