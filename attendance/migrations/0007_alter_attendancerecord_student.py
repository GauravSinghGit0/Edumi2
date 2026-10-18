"""
attendance/migrations/0007_alter_attendancerecord_student.py

Changes AttendanceRecord.student on_delete from CASCADE to PROTECT to ensure
historical biometric attendance records are never accidentally deleted.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('attendance', '0006_alter_studentengagementsnapshot_emotion'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attendancerecord',
            name='student',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='attendance_records',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
