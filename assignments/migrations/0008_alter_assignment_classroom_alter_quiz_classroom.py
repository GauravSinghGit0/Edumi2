from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0001_initial'),
        ('assignments', '0007_alter_assignmentsubmission_student_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='assignment',
                    name='classroom',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='academics.classroom'),
                ),
                migrations.AlterField(
                    model_name='quiz',
                    name='classroom',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quizzes', to='academics.classroom'),
                ),
            ],
            database_operations=[]
        ),
    ]
