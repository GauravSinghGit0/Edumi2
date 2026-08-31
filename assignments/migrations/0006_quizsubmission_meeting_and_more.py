# Generated for Live Meeting Quiz integration

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0005_alter_assignmentquestionfile_file_and_more'),
        ('meetings', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='quizsubmission',
            name='meeting',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='quiz_submissions', to='meetings.meeting'),
        ),
        migrations.AddField(
            model_name='quizsubmission',
            name='is_live_meeting_quiz',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='quizsubmission',
            name='tab_switch_count',
            field=models.IntegerField(default=0, help_text='Number of anti-cheating tab switch violations'),
        ),
        migrations.AlterUniqueTogether(
            name='quizsubmission',
            unique_together={('quiz', 'student', 'meeting')},
        ),
    ]
