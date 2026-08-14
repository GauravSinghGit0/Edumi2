from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0003_studentfaceprofile_face_photo'),
        ('meetings', '0005_add_left_status'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EngagementReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('generated_at', models.DateTimeField(auto_now_add=True)),
                ('student_data', models.JSONField(default=list)),
                ('class_engagement_score', models.FloatField(default=0.0)),
                ('classroom', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='engagement_reports', to='meetings.classroom')),
                ('meeting', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='engagement_report', to='meetings.meeting')),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='engagement_reports', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-generated_at']},
        ),
        migrations.CreateModel(
            name='StudentEngagementSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('emotion', models.CharField(choices=[('focused', 'Focused'), ('happy', 'Happy'), ('confused', 'Confused'), ('distracted', 'Distracted'), ('absent', 'Not Visible'), ('unknown', 'Unknown')], default='unknown', max_length=20)),
                ('confidence', models.FloatField(default=0.0)),
                ('face_visible', models.BooleanField(default=True)),
                ('meeting', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='engagement_snapshots', to='meetings.meeting')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='engagement_snapshots', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['timestamp'], 'indexes': [models.Index(fields=['meeting', 'student'], name='attendance__meeting_7e3c2a_idx')]},
        ),
    ]
