from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0001_initial'),
        ('attendance', '0009_remove_faceduplicatereview_matched_user_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='attendancerecord',
                    name='classroom',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_records', to='academics.classroom'),
                ),
                migrations.AlterField(
                    model_name='attendancesettings',
                    name='classroom',
                    field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_settings', to='academics.classroom'),
                ),
                migrations.AlterField(
                    model_name='classschedule',
                    name='classroom',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedules', to='academics.classroom'),
                ),
                migrations.AlterField(
                    model_name='engagementreport',
                    name='classroom',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='engagement_reports', to='academics.classroom'),
                ),
            ],
            database_operations=[]
        ),
    ]
