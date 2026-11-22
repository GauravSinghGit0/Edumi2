from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0001_initial'),
        ('meetings', '0018_alter_classroom_teacher'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='meeting',
                    name='classroom',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='meetings', to='academics.classroom'),
                ),
            ],
            database_operations=[]
        ),
    ]
