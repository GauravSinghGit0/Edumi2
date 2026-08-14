"""
Generates an EngagementReport from StudentEngagementSnapshot rows
after a meeting ends.
"""
import logging
from collections import Counter
from django.utils import timezone

logger = logging.getLogger('attendance.engagement')


def generate_engagement_report(meeting_id: int):
    """
    Called after meeting ends. Aggregates snapshots → EngagementReport.
    Safe to call multiple times (uses update_or_create).
    """
    from meetings.models import Meeting
    from .models import StudentEngagementSnapshot, EngagementReport

    try:
        meeting = Meeting.objects.select_related('classroom', 'teacher').get(id=meeting_id)
    except Meeting.DoesNotExist:
        logger.error(f'Meeting {meeting_id} not found for engagement report')
        return

    snapshots = StudentEngagementSnapshot.objects.filter(meeting=meeting).select_related('student')

    if not snapshots.exists():
        # Create empty report so teacher sees something
        EngagementReport.objects.update_or_create(
            meeting=meeting,
            defaults={
                'classroom':              meeting.classroom,
                'teacher':                meeting.teacher,
                'student_data':           [],
                'class_engagement_score': 0.0,
            }
        )
        return

    # Group by student
    by_student = {}
    for snap in snapshots:
        uid = snap.student_id
        if uid not in by_student:
            by_student[uid] = {
                'student':   snap.student,
                'emotions':  [],
                'confs':     [],
                'visible':   0,
                'total':     0,
            }
        by_student[uid]['emotions'].append(snap.emotion)
        by_student[uid]['confs'].append(snap.confidence)
        by_student[uid]['total'] += 1
        if snap.face_visible:
            by_student[uid]['visible'] += 1

    student_data   = []
    total_score    = 0.0
    student_count  = 0

    for uid, d in by_student.items():
        student = d['student']
        emotion_counts = Counter(d['emotions'])
        dominant_emotion = emotion_counts.most_common(1)[0][0]

        # Engagement score: focused=1.0, happy=0.9, confused=0.6, distracted=0.3, unknown/absent=0.1
        EMOTION_WEIGHTS = {
            'focused': 1.0, 'happy': 0.9, 'confused': 0.6,
            'distracted': 0.3, 'absent': 0.1, 'unknown': 0.1,
        }
        weighted = sum(EMOTION_WEIGHTS.get(e, 0.1) for e in d['emotions'])
        engagement_score = round((weighted / d['total']) * 100, 1) if d['total'] else 0

        presence_pct = round(d['visible'] / d['total'] * 100, 1) if d['total'] else 0

        student_data.append({
            'user_id':         uid,
            'name':            student.get_full_name() or student.username,
            'username':        student.username,
            'dominant_emotion': dominant_emotion,
            'emotion_counts':  dict(emotion_counts),
            'engagement_score': engagement_score,
            'presence_pct':    presence_pct,
            'avg_confidence':  round(sum(d['confs']) / len(d['confs']), 3) if d['confs'] else 0,
            'total_snapshots': d['total'],
        })

        total_score   += engagement_score
        student_count += 1

    class_score = round(total_score / student_count, 1) if student_count else 0.0

    EngagementReport.objects.update_or_create(
        meeting=meeting,
        defaults={
            'classroom':              meeting.classroom,
            'teacher':                meeting.teacher,
            'student_data':           student_data,
            'class_engagement_score': class_score,
        }
    )
    logger.info(f'Engagement report generated for meeting {meeting.meeting_code}, score={class_score}')
