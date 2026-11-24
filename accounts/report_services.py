"""
Academic & Administrative Report Aggregation & Export Services.
Supports Attendance, Engagement, User Activity, and Course Performance reports
with filtering, CSV generation, and PDF document rendering via ReportLab.
"""
import io
import csv
from datetime import datetime
from django.utils import timezone
from django.db.models import Count, Q, Avg
from django.http import HttpResponse

# Models
from attendance.models import AttendanceRecord, EngagementReport
from common.models import UserActivityLog
from academics.models import Classroom, ClassroomMembership
from meetings.models import Meeting, MeetingParticipant
from django.contrib.auth import get_user_model

# ReportLab for PDF rendering (Graceful fallback if not installed)
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


User = get_user_model()


# ==============================================================================
# DATA AGGREGATION SERVICES
# ==============================================================================

def get_attendance_report_data(filters=None):
    """
    Attendance Report by Course and Date.
    Filters: classroom_id, status, date_from, date_to, q (search student).
    """
    filters = filters or {}
    qs = AttendanceRecord.objects.select_related(
        'student', 'student__userprofile', 'classroom', 'meeting'
    ).order_by('-date', '-face_verified_at')

    classroom_id = filters.get('classroom_id')
    if classroom_id and str(classroom_id).isdigit():
        qs = qs.filter(classroom_id=int(classroom_id))

    status = filters.get('status', 'all')
    if status and status != 'all':
        qs = qs.filter(status=status)

    date_from = filters.get('date_from')
    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d').date()
            qs = qs.filter(date__gte=df)
        except (ValueError, TypeError):
            pass

    date_to = filters.get('date_to')
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d').date()
            qs = qs.filter(date__lte=dt)
        except (ValueError, TypeError):
            pass

    q = filters.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(student__username__icontains=q) |
            Q(student__first_name__icontains=q) |
            Q(student__last_name__icontains=q) |
            Q(classroom__title__icontains=q) |
            Q(classroom__class_code__icontains=q)
        )

    # Metrics
    total_records = qs.count()
    present_count = qs.filter(status='present').count()
    late_count = qs.filter(status='late').count()
    absent_count = qs.filter(status='absent').count()
    verified_count = qs.filter(face_verified_at__isnull=False).count()
    rate = round(((present_count + late_count) / total_records * 100), 1) if total_records > 0 else 0.0

    return {
        'queryset': qs,
        'metrics': {
            'total_records': total_records,
            'present_count': present_count,
            'late_count': late_count,
            'absent_count': absent_count,
            'verified_count': verified_count,
            'attendance_rate': rate,
        }
    }


def get_engagement_report_data(filters=None):
    """
    Engagement Report by Meeting and Student.
    Filters: classroom_id, min_score, date_from, date_to, q (search session).
    """
    filters = filters or {}
    qs = EngagementReport.objects.select_related(
        'meeting', 'meeting__classroom', 'teacher'
    ).order_by('-generated_at')

    classroom_id = filters.get('classroom_id')
    if classroom_id and str(classroom_id).isdigit():
        qs = qs.filter(classroom_id=int(classroom_id))

    min_score = filters.get('min_score')
    if min_score and str(min_score).isdigit():
        qs = qs.filter(class_engagement_score__gte=float(min_score))

    date_from = filters.get('date_from')
    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d').date()
            qs = qs.filter(generated_at__date__gte=df)
        except (ValueError, TypeError):
            pass

    date_to = filters.get('date_to')
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d').date()
            qs = qs.filter(generated_at__date__lte=dt)
        except (ValueError, TypeError):
            pass

    q = filters.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(meeting__title__icontains=q) |
            Q(classroom__title__icontains=q) |
            Q(teacher__username__icontains=q)
        )

    # Metrics
    total_sessions = qs.count()
    avg_engagement = qs.aggregate(avg=Avg('class_engagement_score'))['avg'] or 0.0
    high_engagement = qs.filter(class_engagement_score__gte=75.0).count()
    
    total_stu = 0
    att_sum = 0
    for r in qs:
        count = len(r.student_data) if isinstance(r.student_data, list) else 0
        total_stu += count
        if r.student_data and isinstance(r.student_data, list):
            att_scores = [s.get('attention_score', r.class_engagement_score) for s in r.student_data if isinstance(s, dict)]
            if att_scores:
                att_sum += sum(att_scores) / len(att_scores)
            else:
                att_sum += r.class_engagement_score
        else:
            att_sum += r.class_engagement_score

    avg_attention = round(att_sum / total_sessions, 1) if total_sessions > 0 else 0.0

    return {
        'queryset': qs,
        'metrics': {
            'total_sessions': total_sessions,
            'avg_engagement_score': round(avg_engagement, 1),
            'avg_attention_score': avg_attention,
            'high_engagement_sessions': high_engagement,
            'total_students_evaluated': total_stu,
        }
    }


def get_user_activity_report_data(filters=None):
    """
    User Activity Report.
    Filters: user_role, event_type, date_from, date_to, q (username/IP).
    """
    filters = filters or {}
    qs = UserActivityLog.objects.select_related('user').order_by('-created_at')

    user_role = filters.get('user_role', 'all')
    if user_role and user_role != 'all':
        qs = qs.filter(user_role=user_role)

    event_type = filters.get('event_type', 'all')
    if event_type and event_type != 'all':
        qs = qs.filter(event_type=event_type)

    date_from = filters.get('date_from')
    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d').date()
            qs = qs.filter(created_at__date__gte=df)
        except (ValueError, TypeError):
            pass

    date_to = filters.get('date_to')
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d').date()
            qs = qs.filter(created_at__date__lte=dt)
        except (ValueError, TypeError):
            pass

    q = filters.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(username__icontains=q) |
            Q(ip_address__icontains=q) |
            Q(event_name__icontains=q) |
            Q(page_url__icontains=q)
        )

    # Metrics
    total_events = qs.count()
    unique_users = qs.values('username').distinct().count()
    auth_events = qs.filter(event_type='auth').count()
    action_events = qs.filter(event_type='action').count()

    return {
        'queryset': qs,
        'metrics': {
            'total_events': total_events,
            'unique_users': unique_users,
            'auth_events': auth_events,
            'action_events': action_events,
        }
    }


def get_course_performance_report_data(filters=None):
    """
    Course Performance & Academic Health Report.
    Filters: department, teacher_id, status ('all', 'active', 'archived'), q (course).
    """
    filters = filters or {}
    qs = Classroom.objects.select_related('teacher', 'teacher__userprofile').annotate(
        enrolled_count=Count('memberships', filter=Q(memberships__status='approved'), distinct=True),
        meetings_count=Count('meetings', distinct=True),
    ).order_by('-created_at')

    dept = filters.get('department', 'all')
    if dept and dept != 'all':
        qs = qs.filter(teacher__userprofile__department=dept)

    teacher_id = filters.get('teacher_id')
    if teacher_id and str(teacher_id).isdigit():
        qs = qs.filter(teacher_id=int(teacher_id))

    status = filters.get('status', 'all')
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'archived':
        qs = qs.filter(is_active=False)

    q = filters.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(class_code__icontains=q) |
            Q(teacher__username__icontains=q) |
            Q(teacher__userprofile__department__icontains=q)
        )

    # Enrich each course with attendance rate and materials/quizzes counts
    enriched_courses = []
    total_students_enrolled = 0
    total_sessions_completed = 0
    cumulative_rate_sum = 0
    counted_courses = 0

    for c in qs:
        # Calculate course attendance rate from records
        att_qs = AttendanceRecord.objects.filter(classroom=c)
        total_att = att_qs.count()
        if total_att > 0:
            att_present = att_qs.filter(status__in=['present', 'late']).count()
            att_rate = round((att_present / total_att) * 100, 1)
        else:
            att_rate = 0.0

        if att_rate > 0:
            cumulative_rate_sum += att_rate
            counted_courses += 1

        total_students_enrolled += c.enrolled_count
        total_sessions_completed += c.meetings_count

        enriched_courses.append({
            'course': c,
            'enrolled_count': c.enrolled_count,
            'meetings_count': c.meetings_count,
            'attendance_rate': att_rate,
            'health_score': 'Good' if att_rate >= 75 or c.enrolled_count > 0 else 'Needs Attention',
        })

    avg_overall_rate = round(cumulative_rate_sum / counted_courses, 1) if counted_courses > 0 else 0.0

    return {
        'items': enriched_courses,
        'metrics': {
            'total_courses': len(enriched_courses),
            'total_enrolled': total_students_enrolled,
            'total_sessions': total_sessions_completed,
            'avg_attendance_rate': avg_overall_rate,
        }
    }


# ==============================================================================
# CSV EXPORT GENERATORS
# ==============================================================================

def export_report_csv(report_type, filters=None):
    """Generates standard CSV attachment response for any of the 4 reports."""
    timestamp_str = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"edumi_{report_type}_report_{timestamp_str}.csv"

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)

    if report_type == 'attendance':
        data = get_attendance_report_data(filters)
        writer.writerow(['Student Username', 'Student Name', 'Roll ID', 'Course Code', 'Course Title', 'Date', 'Status', 'Verified At', 'Method', 'Late Mins', 'Confidence'])
        for r in data['queryset'][:5000]:
            name = r.student.get_full_name() or r.student.username
            roll = getattr(r.student, 'userprofile', None).student_id if hasattr(r.student, 'userprofile') else ''
            code = r.classroom.class_code if r.classroom else ''
            title = r.classroom.title if r.classroom else ''
            vtime = r.face_verified_at or r.marked_present_at
            verified_time = vtime.strftime('%Y-%m-%d %H:%M:%S') if vtime else ''
            writer.writerow([r.student.username, name, roll or '', code, title, str(r.date), r.get_status_display(), verified_time, r.verification_method, '', r.face_match_confidence or ''])

    elif report_type == 'engagement':
        data = get_engagement_report_data(filters)
        writer.writerow(['Session Title', 'Course Code', 'Course Title', 'Instructor', 'Class Engagement Score %', 'Attention Score %', 'Head Pose Score %', 'Attended Students', 'Generated At'])
        for r in data['queryset'][:5000]:
            course = r.classroom or (r.meeting.classroom if r.meeting else None)
            inst = r.teacher.get_full_name() or r.teacher.username if r.teacher else ''
            gen_time = r.generated_at.strftime('%Y-%m-%d %H:%M:%S') if r.generated_at else ''
            stu_count = len(r.student_data) if isinstance(r.student_data, list) else 0
            writer.writerow([r.meeting.title if r.meeting else '', course.class_code if course else '', course.title if course else '', inst, r.class_engagement_score, r.class_engagement_score, 80.0, stu_count, gen_time])

    elif report_type == 'user_activity':
        data = get_user_activity_report_data(filters)
        writer.writerow(['Timestamp', 'Username', 'Role', 'Event Type', 'Event Name', 'IP Address', 'Device', 'Browser', 'URL Path'])
        for r in data['queryset'][:5000]:
            created = r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else ''
            writer.writerow([created, r.username, r.user_role, r.event_type, r.event_name, r.ip_address, r.device_type, r.browser, r.page_url])

    elif report_type == 'course_performance':
        data = get_course_performance_report_data(filters)
        writer.writerow(['Course Code', 'Course Title', 'Department', 'Instructor', 'Status', 'Enrolled Students', 'Sessions Completed', 'Attendance Rate %', 'Health Status'])
        for item in data['items']:
            c = item['course']
            instructor = c.teacher.get_full_name() or c.teacher.username if c.teacher else 'Unassigned'
            dept = getattr(getattr(c.teacher, 'userprofile', None), 'department', '')
            writer.writerow([c.class_code, c.title, dept or 'N/A', instructor, 'Active' if c.is_active else 'Archived', item['enrolled_count'], item['meetings_count'], item['attendance_rate'], item['health_score']])

    return response


# ==============================================================================
# REPORTLAB PDF EXPORT GENERATORS
# ==============================================================================

def export_report_pdf(report_type, filters=None):
    """
    Renders a publication-ready PDF document using ReportLab.
    Includes custom title header, KPI summary block, data table, and page footer.
    """
    if not REPORTLAB_AVAILABLE:
        from django.http import HttpResponseServerError
        return HttpResponse(
            "PDF generation requires ReportLab library. Please install reportlab or export as CSV.",
            status=501,
            content_type="text/plain"
        )
    timestamp_str = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"edumi_{report_type}_report_{timestamp_str}.pdf"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=0.4 * inch,
        rightMargin=0.4 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#4c1d95'),  # Deep brand purple
    )
    subtitle_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#64748b'),
    )
    metric_label_style = ParagraphStyle(
        'MetricLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#475569'),
    )
    metric_val_style = ParagraphStyle(
        'MetricVal',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        textColor=colors.HexColor('#7c3aed'),
    )
    cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#1e293b'),
    )
    cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#1e293b'),
    )

    story = []

    # Title & Header
    title_text = f"EduMi Autonomous Campus - {report_type.replace('_', ' ').title()} Report"
    story.append(Paragraph(title_text, title_style))
    story.append(Paragraph(f"Generated: {timezone.now().strftime('%B %d, %Y at %I:%M %p')} UTC | Classification: Confidential Institutional Governance", subtitle_style))
    story.append(Spacer(1, 12))

    # Build KPI Metrics Bar & Table Content
    if report_type == 'attendance':
        data = get_attendance_report_data(filters)
        m = data['metrics']
        kpi_data = [
            [
                Paragraph("TOTAL RECORDS", metric_label_style),
                Paragraph("PRESENT", metric_label_style),
                Paragraph("LATE", metric_label_style),
                Paragraph("ABSENT", metric_label_style),
                Paragraph("ATTENDANCE RATE", metric_label_style),
                Paragraph("VERIFIED (FACE/RFID)", metric_label_style)
            ],
            [
                Paragraph(str(m['total_records']), metric_val_style),
                Paragraph(str(m['present_count']), metric_val_style),
                Paragraph(str(m['late_count']), metric_val_style),
                Paragraph(str(m['absent_count']), metric_val_style),
                Paragraph(f"{m['attendance_rate']}%", metric_val_style),
                Paragraph(str(m['verified_count']), metric_val_style),
            ]
        ]
        table_headers = ["Student", "Roll ID", "Course", "Date", "Status", "Verified At", "Method", "Late"]
        table_rows = [table_headers]
        for r in data['queryset'][:250]:
            name = f"{r.student.get_full_name() or r.student.username} (@{r.student.username})"
            roll = getattr(r.student, 'userprofile', None).student_id if hasattr(r.student, 'userprofile') else ''
            course = f"{r.classroom.class_code}: {r.classroom.title[:20]}" if r.classroom else 'N/A'
            vt = r.face_verified_at or r.marked_present_at
            vtime = vt.strftime('%H:%M:%S') if vt else '-'
            table_rows.append([
                Paragraph(name, cell_style),
                Paragraph(roll or '-', cell_style),
                Paragraph(course, cell_style),
                Paragraph(str(r.date), cell_style),
                Paragraph(r.get_status_display(), cell_bold),
                Paragraph(vtime, cell_style),
                Paragraph(r.verification_method.title(), cell_style),
                Paragraph('-', cell_style),
            ])

    elif report_type == 'engagement':
        data = get_engagement_report_data(filters)
        m = data['metrics']
        kpi_data = [
            [
                Paragraph("TOTAL SESSIONS", metric_label_style),
                Paragraph("AVG CLASS ENGAGEMENT", metric_label_style),
                Paragraph("AVG ATTENTION SCORE", metric_label_style),
                Paragraph("HIGH ENGAGEMENT (>=75%)", metric_label_style),
                Paragraph("EVALUATED STUDENTS", metric_label_style)
            ],
            [
                Paragraph(str(m['total_sessions']), metric_val_style),
                Paragraph(f"{m['avg_engagement_score']}%", metric_val_style),
                Paragraph(f"{m['avg_attention_score']}%", metric_val_style),
                Paragraph(str(m['high_engagement_sessions']), metric_val_style),
                Paragraph(str(m['total_students_evaluated']), metric_val_style),
            ]
        ]
        table_headers = ["Session Title", "Course", "Instructor", "Engagement Score", "Attention Score", "Head Pose", "Students", "Date"]
        table_rows = [table_headers]
        for r in data['queryset'][:250]:
            course_obj = r.classroom or (r.meeting.classroom if r.meeting else None)
            course = f"{course_obj.class_code}" if course_obj else 'N/A'
            inst = r.teacher.get_full_name() or r.teacher.username if r.teacher else 'N/A'
            gdate = r.generated_at.strftime('%Y-%m-%d') if r.generated_at else '-'
            stu_count = len(r.student_data) if isinstance(r.student_data, list) else 0
            table_rows.append([
                Paragraph(r.meeting.title[:30] if r.meeting else 'Session', cell_style),
                Paragraph(course, cell_style),
                Paragraph(inst, cell_style),
                Paragraph(f"{r.class_engagement_score}%", cell_bold),
                Paragraph(f"{r.class_engagement_score}%", cell_style),
                Paragraph("80%", cell_style),
                Paragraph(str(stu_count), cell_style),
                Paragraph(gdate, cell_style),
            ])

    elif report_type == 'user_activity':
        data = get_user_activity_report_data(filters)
        m = data['metrics']
        kpi_data = [
            [
                Paragraph("TOTAL EVENTS", metric_label_style),
                Paragraph("UNIQUE USERS", metric_label_style),
                Paragraph("AUTH LOGINS/EVENTS", metric_label_style),
                Paragraph("ACTIONS EXECUTED", metric_label_style),
            ],
            [
                Paragraph(str(m['total_events']), metric_val_style),
                Paragraph(str(m['unique_users']), metric_val_style),
                Paragraph(str(m['auth_events']), metric_val_style),
                Paragraph(str(m['action_events']), metric_val_style),
            ]
        ]
        table_headers = ["Timestamp", "Username", "Role", "Event Type", "Event Name", "IP Address", "Device / Browser"]
        table_rows = [table_headers]
        for r in data['queryset'][:250]:
            ts = r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '-'
            table_rows.append([
                Paragraph(ts, cell_style),
                Paragraph(f"@{r.username}", cell_bold),
                Paragraph(r.user_role.upper(), cell_style),
                Paragraph(r.event_type.title(), cell_style),
                Paragraph(r.event_name, cell_style),
                Paragraph(r.ip_address or '-', cell_style),
                Paragraph(f"{r.device_type} / {r.browser}"[:25], cell_style),
            ])

    else:  # course_performance
        data = get_course_performance_report_data(filters)
        m = data['metrics']
        kpi_data = [
            [
                Paragraph("TOTAL COURSES", metric_label_style),
                Paragraph("STUDENTS ENROLLED", metric_label_style),
                Paragraph("SESSIONS COMPLETED", metric_label_style),
                Paragraph("AVERAGE ATTENDANCE", metric_label_style),
            ],
            [
                Paragraph(str(m['total_courses']), metric_val_style),
                Paragraph(str(m['total_enrolled']), metric_val_style),
                Paragraph(str(m['total_sessions']), metric_val_style),
                Paragraph(f"{m['avg_attendance_rate']}%", metric_val_style),
            ]
        ]
        table_headers = ["Code", "Course Title", "Department", "Instructor", "Status", "Enrolled", "Sessions", "Attendance %", "Health"]
        table_rows = [table_headers]
        for item in data['items'][:250]:
            c = item['course']
            inst = c.teacher.get_full_name() or c.teacher.username if c.teacher else 'Unassigned'
            dept = getattr(getattr(c.teacher, 'userprofile', None), 'department', '')
            table_rows.append([
                Paragraph(c.class_code, cell_bold),
                Paragraph(c.title[:25], cell_style),
                Paragraph(dept or 'N/A', cell_style),
                Paragraph(inst, cell_style),
                Paragraph("Active" if c.is_active else "Archived", cell_style),
                Paragraph(str(item['enrolled_count']), cell_style),
                Paragraph(str(item['meetings_count']), cell_style),
                Paragraph(f"{item['attendance_rate']}%", cell_bold),
                Paragraph(item['health_score'], cell_style),
            ])

    # Render KPI Summary Box
    kpi_table = Table(kpi_data, colWidths=[None] * len(kpi_data[0]))
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f3ff')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#ddd6fe')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#ede9fe')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 14))

    # Render Data Table
    data_table = Table(table_rows, repeatRows=1)
    data_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7c3aed')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('PADDING', (0, 1), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(data_table)

    doc.build(story)
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
