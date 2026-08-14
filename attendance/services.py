"""
Service layer for Attendance app.
Contains business logic for reports and face registration helpers.
"""
from django.utils import timezone
from django.db.models import Count, Q
from .models import AttendanceRecord, StudentFaceProfile, AttendanceSettings, ClassSchedule

def get_daily_report_context(classroom, report_date):
    """Generate data for the daily attendance report."""
    memberships = classroom.get_approved_memberships()
    
    records_qs = AttendanceRecord.objects.filter(
        classroom=classroom, date=report_date
    ).select_related('student', 'student__userprofile')
    
    records_map = {r.student_id: r for r in records_qs}
    
    rows = []
    for m in memberships:
        rec = records_map.get(m.student_id)
        rows.append({
            'student':    m.student,
            'record':     rec,
            'status':     rec.status if rec else 'absent',
            'time_in':    rec.marked_present_at if rec else None,
            'confidence': round(rec.face_match_confidence * 100, 1) if rec else 0,
            'method':     rec.verification_method if rec else '—',
        })
        
    present_count = sum(1 for r in rows if r['status'] == 'present')
    late_count    = sum(1 for r in rows if r['status'] == 'late')
    
    return {
        'rows': rows,
        'present_count': present_count,
        'late_count': late_count,
        'absent_count': len(rows) - present_count - late_count,
        'total': len(rows),
    }

def get_classroom_attendance_stats(classroom):
    """Aggregate overall attendance stats for all students in a classroom."""
    memberships = classroom.get_approved_memberships()
    student_ids = [m.student_id for m in memberships]
    
    # Aggregate attendance
    att_map = {
        r['student_id']: r
        for r in AttendanceRecord.objects.filter(classroom=classroom)
            .values('student_id')
            .annotate(
                total=Count('id'),
                present=Count('id', filter=Q(status__in=['present', 'late']))
            )
    }
    
    # Pre-fetch face profiles
    face_profile_map = {
        p.student_id: p.is_active 
        for p in StudentFaceProfile.objects.filter(student_id__in=student_ids)
    }
    
    rows = []
    for m in memberships:
        agg = att_map.get(m.student_id, {'total': 0, 'present': 0})
        total = agg['total']
        present = agg['present']
        
        rows.append({
            'student':         m.student,
            'total':           total,
            'present':         present,
            'absent':          total - present,
            'percentage':      round(present / total * 100) if total else 0,
            'face_registered': face_profile_map.get(m.student_id, False),
        })
        
    rows.sort(key=lambda x: x['percentage'])
    return rows
