"""
assignments/migrations/0007_alter_assignmentsubmission_student_and_more.py

Changes AssignmentSubmission.student and QuizSubmission.student on_delete
from CASCADE to PROTECT to ensure historical homework submissions, exams,
and marks are never destroyed on user deactivation.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('assignments', '0006_quizsubmission_meeting_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='assignmentsubmission',
            name='student',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='assignment_submissions',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='quizsubmission',
            name='student',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='quiz_submissions',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
