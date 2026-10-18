"""
meetings/migrations/0018_alter_classroom_teacher.py

Changes Classroom.teacher on_delete from CASCADE to PROTECT to ensure that
a classroom and its entire history (study materials, quizzes, student enrollments)
are not accidentally wiped if a teacher account is deleted.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('meetings', '0017_materialchunk_embedding_vector'),
    ]

    operations = [
        migrations.AlterField(
            model_name='classroom',
            name='teacher',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='created_classrooms',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
