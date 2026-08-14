# Migration: sync Django model with columns that already exist in the DB.
# The video_editing/editor sub-app added active, parameters, resource_file,
# trim_start, trim_end, and video_file via its own migrations before it was
# removed.  Those columns are already present in SQLite, so we use
# SeparateDatabaseAndState to record them in Django's migration graph
# WITHOUT issuing any ALTER TABLE statements.

from django.db import migrations, models
import video_editing.models


class Migration(migrations.Migration):

    dependencies = [
        ('video_editing', '0002_videoproject_timeline_state_projectasset'),
    ]

    operations = [
        migrations.AddField(
            model_name='editoperation',
            name='active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='editoperation',
            name='parameters',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='editoperation',
            name='resource_file',
            field=models.FileField(
                blank=True, null=True,
                upload_to=video_editing.models.project_upload_path,
            ),
        ),
        migrations.AddField(
            model_name='editoperation',
            name='trim_end',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='editoperation',
            name='trim_start',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='editoperation',
            name='video_file',
            field=models.FileField(
                blank=True, null=True,
                upload_to=video_editing.models.project_upload_path,
            ),
        ),
    ]
