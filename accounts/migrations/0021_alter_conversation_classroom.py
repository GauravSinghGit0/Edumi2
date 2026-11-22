from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0001_initial'),
        ('accounts', '0020_userprofile_ssot_constraints_and_soft_delete'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='conversation',
                    name='classroom',
                    field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='conversation', to='academics.classroom'),
                ),
            ],
            database_operations=[]
        ),
    ]
