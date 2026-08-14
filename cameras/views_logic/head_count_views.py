
import csv
import requests
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.db.models import Avg, Max, Min, Count
from ..models import Camera, HeadCountLog, HeadCountSession, CameraPermission
from .utils import is_admin, can_view_camera
from ..head_count_service import head_count_manager
from mobile_cameras.models import MobileCamera, MobileCameraPermission


@login_required
def head_count_dashboard(request):
    """Dashboard for head counting - shows all cameras with head count capability"""
    import logging
    logger = logging.getLogger('cameras')

    # Get cameras based on user role
    if is_admin(request.user):
        rtsp_cameras = Camera.objects.filter(is_active=True)
        mobile_cameras = MobileCamera.objects.filter(is_active=True)
    elif hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'teacher':
        camera_ids = CameraPermission.objects.filter(teacher=request.user).values_list('camera_id', flat=True)
        rtsp_cameras = Camera.objects.filter(id__in=camera_ids, is_active=True)

        mobile_camera_ids = MobileCameraPermission.objects.filter(teacher=request.user).values_list('mobile_camera_id', flat=True)
        mobile_cameras = MobileCamera.objects.filter(id__in=mobile_camera_ids, is_active=True)
    else:
        rtsp_cameras = Camera.objects.none()
        mobile_cameras = MobileCamera.objects.none()

    # PROXIED: Get active sessions from the dedicated camera service
    active_sessions = {}
    try:
        service_url = 'http://localhost:8003/head-count/active-sessions/'
        response = requests.get(service_url, timeout=2)
        if response.status_code == 200:
            active_sessions = response.json().get('active_sessions', {})
    except Exception as e:
        logger.error(f"Failed to fetch active headcount sessions from service: {e}")

    # Add session status to cameras based on proxied data
    for camera in rtsp_cameras:
        session_key = f"rtsp_{camera.id}"
        camera.has_active_session = session_key in active_sessions
        camera.camera_type = 'rtsp'

    for camera in mobile_cameras:
        session_key = f"mobile_{camera.id}"
        camera.has_active_session = session_key in active_sessions
        camera.camera_type = 'mobile'

    # Get recent head count logs (Database is shared, so this is fine)
    recent_logs = HeadCountLog.objects.all().order_by('-timestamp')[:10]

    context = {
        'rtsp_cameras': rtsp_cameras,
        'mobile_cameras': mobile_cameras,
        'active_sessions': active_sessions,
        'recent_logs': recent_logs,
    }
    return render(request, 'cameras/head_count_dashboard.html', context)


@login_required
def start_head_count(request, camera_type, camera_id):
    """Start head counting session - proxies request to dedicated camera service"""
    # Check permissions first
    if camera_type == 'rtsp':
        camera = get_object_or_404(Camera, id=camera_id)
    elif camera_type == 'mobile':
        camera = get_object_or_404(MobileCamera, id=camera_id)
    else:
        return JsonResponse({'error': 'Invalid camera type'}, status=400)

    if not can_view_camera(request.user, camera):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # Prepare parameters for the microservice
    classroom_id = request.POST.get('classroom_id') or request.GET.get('classroom_id') or ''
    interval = request.POST.get('interval') or request.GET.get('interval') or '30'

    try:
        service_url = f'http://localhost:8003/head-count/start/{camera_type}/{camera_id}/'
        params = {
            'user_id': request.user.id,
            'classroom_id': classroom_id,
            'interval': interval
        }
        response = requests.get(service_url, params=params, timeout=10)
        return JsonResponse(response.json(), status=response.status_code)
    except Exception as e:
        return JsonResponse({'error': f'Camera service error: {str(e)}'}, status=500)


@login_required
def stop_head_count(request, camera_type, camera_id):
    """Stop head counting session - proxies request to dedicated camera service"""
    try:
        service_url = f'http://localhost:8003/head-count/stop/{camera_type}/{camera_id}/'
        response = requests.get(service_url, timeout=10)
        return JsonResponse(response.json(), status=response.status_code)
    except Exception as e:
        return JsonResponse({'error': f'Camera service error: {str(e)}'}, status=500)


@login_required
def head_count_logs(request):
    """View head count logs with filtering"""
    logs = HeadCountLog.objects.all()

    # Filter by camera type
    camera_type = request.GET.get('camera_type')
    if camera_type:
        logs = logs.filter(camera_type=camera_type)

    # Filter by camera
    camera_id = request.GET.get('camera_id')
    if camera_id:
        logs = logs.filter(camera_id=camera_id)

    # Filter by classroom
    classroom_id = request.GET.get('classroom')
    if classroom_id:
        logs = logs.filter(classroom_id=classroom_id)

    # Filter by date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        logs = logs.filter(date__gte=date_from)
    if date_to:
        logs = logs.filter(date__lte=date_to)

    # Filter by hour
    hour = request.GET.get('hour')
    if hour:
        logs = logs.filter(hour=int(hour))

    # Calculate statistics
    stats = logs.aggregate(
        total_records=Count('id'),
        avg_head_count=Avg('head_count'),
        max_head_count=Max('head_count'),
        min_head_count=Min('head_count'),
        avg_confidence=Avg('confidence_score')
    )

    # Group by date for chart data
    date_stats = logs.values('date').annotate(
        avg_count=Avg('head_count'),
        max_count=Max('head_count'),
        total=Count('id')
    ).order_by('-date')[:30]

    # Group by hour for time-wise analysis
    hour_stats = logs.values('hour').annotate(
        avg_count=Avg('head_count'),
        total=Count('id')
    ).order_by('hour')

    # Get classrooms for filter dropdown
    from meetings.models import Classroom
    classrooms = Classroom.objects.all()

    context = {
        'logs': logs[:100],  # Limit to 100 records
        'stats': stats,
        'date_stats': date_stats,
        'hour_stats': hour_stats,
        'classrooms': classrooms,
        'filter_params': request.GET,
    }
    return render(request, 'cameras/head_count_logs.html', context)


@login_required
def head_count_log_detail(request, log_id):
    """View details of a specific head count log"""
    log = get_object_or_404(HeadCountLog, id=log_id)

    context = {
        'log': log,
    }
    return render(request, 'cameras/head_count_log_detail.html', context)


@login_required
def head_count_session_history(request):
    """View history of head counting sessions"""
    sessions = HeadCountSession.objects.all()

    # Filter by status
    status = request.GET.get('status')
    if status:
        sessions = sessions.filter(status=status)

    # Filter by date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        sessions = sessions.filter(started_at__date__gte=date_from)
    if date_to:
        sessions = sessions.filter(started_at__date__lte=date_to)

    context = {
        'sessions': sessions[:50],
    }
    return render(request, 'cameras/head_count_sessions.html', context)


@login_required
def head_count_api(request, camera_type, camera_id):
    """API endpoint to get current head count for a camera"""
    current_count = head_count_manager.get_current_count(camera_type, camera_id)
    is_active = head_count_manager.is_session_active(camera_type, camera_id)

    return JsonResponse({
        'camera_type': camera_type,
        'camera_id': camera_id,
        'is_active': is_active,
        'current_count': current_count,
    })


@login_required
def head_count_report(request):
    """Generate head count reports - class-wise, day-wise, time-wise"""
    # Get filter parameters
    report_type = request.GET.get('report_type', 'daily')
    classroom_id = request.GET.get('classroom')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    logs = HeadCountLog.objects.all()

    # Apply filters
    if classroom_id:
        logs = logs.filter(classroom_id=classroom_id)
    if date_from:
        logs = logs.filter(date__gte=date_from)
    if date_to:
        logs = logs.filter(date__lte=date_to)

    report_data = {}

    if report_type == 'class_wise':
        # Group by classroom
        report_data = logs.values(
            'classroom__title', 'classroom_id'
        ).annotate(
            total_records=Count('id'),
            avg_head_count=Avg('head_count'),
            max_head_count=Max('head_count'),
            min_head_count=Min('head_count'),
        ).order_by('-total_records')

    elif report_type == 'day_wise':
        # Group by date
        report_data = logs.values('date').annotate(
            total_records=Count('id'),
            avg_head_count=Avg('head_count'),
            max_head_count=Max('head_count'),
            min_head_count=Min('head_count'),
        ).order_by('-date')

    elif report_type == 'time_wise':
        # Group by hour
        report_data = logs.values('hour').annotate(
            total_records=Count('id'),
            avg_head_count=Avg('head_count'),
            max_head_count=Max('head_count'),
        ).order_by('hour')

    elif report_type == 'camera_wise':
        # Group by camera
        report_data = logs.values(
            'camera_type', 'camera_id', 'camera_name'
        ).annotate(
            total_records=Count('id'),
            avg_head_count=Avg('head_count'),
            max_head_count=Max('head_count'),
        ).order_by('-total_records')

    # Get classrooms for filter
    from meetings.models import Classroom
    classrooms = Classroom.objects.all()

    context = {
        'report_type': report_type,
        'report_data': report_data,
        'classrooms': classrooms,
        'filter_params': request.GET,
    }
    return render(request, 'cameras/head_count_report.html', context)


@login_required
def export_head_count_csv(request):
    """Export head count logs as CSV"""
    logs = HeadCountLog.objects.all()

    # Apply filters
    camera_type = request.GET.get('camera_type')
    if camera_type:
        logs = logs.filter(camera_type=camera_type)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        logs = logs.filter(date__gte=date_from)
    if date_to:
        logs = logs.filter(date__lte=date_to)

    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="head_count_logs.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Date', 'Time', 'Camera Type', 'Camera Name',
        'Classroom', 'Head Count', 'Confidence', 'Notes'
    ])

    for log in logs:
        writer.writerow([
            log.date,
            log.timestamp.strftime('%H:%M:%S'),
            log.get_camera_type_display(),
            log.camera_name,
            log.classroom.title if log.classroom else 'N/A',
            log.head_count,
            f"{log.confidence_score:.2f}",
            log.notes
        ])

    return response

