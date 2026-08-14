"""
Teacher attendance control views + student's own attendance view:
my_attendance, set_class_schedule, attendance_settings, override_attendance.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from meetings.models import Classroom
from attendance.models import (
    AttendanceRecord, ClassSchedule, AttendanceSettings,
)


@login_required
def my_attendance(request):
    """Student view of their own attendance records across all classrooms."""
    records = AttendanceRecord.objects.filter(
        student=request.user
    ).select_related('meeting', 'classroom').order_by('-date')

    summary = {}
    for rec in records:
        key = rec.classroom_id
        if key not in summary:
            summary[key] = {'classroom': rec.classroom, 'total': 0, 'present': 0, 'absent': 0, 'late': 0}
        summary[key]['total'] += 1
        summary[key][rec.status] = summary[key].get(rec.status, 0) + 1

    for s in summary.values():
        s['percentage'] = round((s['present'] + s.get('late', 0)) / s['total'] * 100) if s['total'] else 0

    return render(request, 'attendance/my_attendance.html', {
        'records': records, 'summary': list(summary.values()), 'page_title': 'My Attendance',
    })


@login_required
def set_class_schedule(request, classroom_id):
    """Teacher sets which days of the week classes are held."""
    classroom = get_object_or_404(Classroom, id=classroom_id, teacher=request.user)
    if request.method == 'POST':
        ClassSchedule.objects.filter(classroom=classroom).delete()
        days = request.POST.getlist('days')
        start_times = request.POST.getlist('start_times')
        end_times = request.POST.getlist('end_times')
        for day, start, end in zip(days, start_times, end_times):
            if day and start and end:
                ClassSchedule.objects.create(
                    classroom=classroom, day_of_week=int(day),
                    start_time=start, end_time=end, created_by=request.user,
                )
        messages.success(request, "Class schedule updated successfully.")
        return redirect('classroom_detail', classroom_id=classroom_id)

    schedules = ClassSchedule.objects.filter(classroom=classroom)
    return render(request, 'attendance/class_schedule.html', {
        'classroom': classroom, 'schedules': schedules,
        'all_days': ClassSchedule.DAY_CHOICES, 'page_title': f'Schedule — {classroom.title}',
    })


@login_required
def attendance_settings_view(request, classroom_id):
    """Teacher configures face-recognition thresholds for a classroom."""
    classroom = get_object_or_404(Classroom, id=classroom_id, teacher=request.user)
    settings_obj, _ = AttendanceSettings.objects.get_or_create(classroom=classroom)
    if request.method == 'POST':
        settings_obj.face_recognition_enabled = 'face_recognition_enabled' in request.POST
        settings_obj.confidence_threshold = float(request.POST.get('confidence_threshold', 0.55))
        settings_obj.presence_duration_seconds = int(request.POST.get('presence_duration_seconds', 30))
        settings_obj.late_threshold_minutes = int(request.POST.get('late_threshold_minutes', 10))
        settings_obj.recognition_interval_seconds = int(request.POST.get('recognition_interval_seconds', 15))
        settings_obj.enforce_schedule = 'enforce_schedule' in request.POST
        settings_obj.save()
        messages.success(request, "Attendance settings saved.")
        return redirect('attendance_settings', classroom_id=classroom_id)

    return render(request, 'attendance/attendance_settings.html', {
        'classroom': classroom, 'att_settings': settings_obj,
        'page_title': f'Attendance Settings — {classroom.title}',
    })


@login_required
@require_POST
def override_attendance(request, record_id):
    """Teacher manually marks a student present/absent/late."""
    record = get_object_or_404(AttendanceRecord, id=record_id)
    if record.classroom.teacher != request.user:
        return JsonResponse({'status': 'forbidden'}, status=403)
    new_status = request.POST.get('status', 'present')
    reason = request.POST.get('reason', '')
    if new_status not in dict(AttendanceRecord.STATUS_CHOICES):
        return JsonResponse({'status': 'error', 'message': 'Invalid status.'}, status=400)
    record.status = new_status
    record.override_reason = reason
    record.overridden_by = request.user
    record.verification_method = 'manual'
    record.save()
    return JsonResponse({'status': 'success', 'new_status': new_status})
