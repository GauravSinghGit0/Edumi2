from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('library', '0001_initial'),
        ('academics', '0001_initial'),
        ('rag_workspace', '0003_alter_raginstructorsetting_options'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='raginstructorsetting',
                    name='classroom',
                    field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='rag_setting', to='academics.classroom'),
                ),
                migrations.AlterField(
                    model_name='ragsession',
                    name='classroom',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='rag_sessions', to='academics.classroom'),
                ),
                migrations.AlterField(
                    model_name='ragsession',
                    name='selected_materials',
                    field=models.ManyToManyField(blank=True, related_name='rag_sessions', to='library.studymaterial'),
                ),
            ],
            database_operations=[]
        ),
    ]
