from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0002_enforce_schedule_default_false'),
    ]

    operations = [
        migrations.AddField(
            model_name='studentfaceprofile',
            name='face_photo',
            field=models.ImageField(blank=True, null=True, upload_to='face_photos/'),
        ),
    ]
