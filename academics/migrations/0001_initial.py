from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('meetings', '0018_alter_classroom_teacher'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Classroom',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('class_code', models.CharField(max_length=20, unique=True)),
                        ('title', models.CharField(max_length=200)),
                        ('password', models.CharField(max_length=128)),
                        ('description', models.TextField(blank=True)),
                        ('auto_approve', models.BooleanField(default=False, help_text='Automatically approve students who join with valid class code & password')),
                        ('is_active', models.BooleanField(default=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('teacher', models.ForeignKey(
                            on_delete=django.db.models.deletion.PROTECT,
                            related_name='created_classrooms',
                            to=settings.AUTH_USER_MODEL
                        )),
                    ],
                    options={
                        'verbose_name': 'Classroom',
                        'verbose_name_plural': 'Classrooms',
                        'db_table': 'meetings_classroom',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='ClassroomMembership',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('status', models.CharField(
                            choices=[
                                ('pending', 'Pending Approval'),
                                ('approved', 'Approved'),
                                ('denied', 'Denied'),
                                ('removed', 'Removed'),
                                ('left', 'Left'),
                            ],
                            default='pending',
                            max_length=20
                        )),
                        ('requested_at', models.DateTimeField(auto_now_add=True)),
                        ('approved_at', models.DateTimeField(blank=True, null=True)),
                        ('approved_by', models.ForeignKey(
                            blank=True,
                            null=True,
                            on_delete=django.db.models.deletion.SET_NULL,
                            related_name='approved_memberships',
                            to=settings.AUTH_USER_MODEL
                        )),
                        ('classroom', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name='memberships',
                            to='academics.classroom'
                        )),
                        ('student', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name='classroom_memberships',
                            to=settings.AUTH_USER_MODEL
                        )),
                    ],
                    options={
                        'verbose_name': 'Classroom Membership',
                        'verbose_name_plural': 'Classroom Memberships',
                        'db_table': 'meetings_classroommembership',
                        'ordering': ['-requested_at'],
                        'unique_together': {('classroom', 'student')},
                    },
                ),
            ],
            database_operations=[]
        ),
    ]
