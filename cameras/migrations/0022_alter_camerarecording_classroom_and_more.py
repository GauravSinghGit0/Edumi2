from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0001_initial'),
        ('cameras', '0021_alter_camera_camera_type'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='camerarecording',
                    name='classroom',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recordings', to='academics.classroom'),
                ),
                migrations.AlterField(
                    model_name='camerarecording',
                    name='classrooms',
                    field=models.ManyToManyField(blank=True, related_name='assigned_recordings', to='academics.classroom'),
                ),
                migrations.AlterField(
                    model_name='headcountlog',
                    name='classroom',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='head_count_logs', to='academics.classroom'),
                ),
                migrations.AlterField(
                    model_name='headcountsession',
                    name='classroom',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='head_count_sessions', to='academics.classroom'),
                ),
            ],
            database_operations=[]
        ),
    ]
