from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('meetings', '0019_alter_meeting_classroom'),
        ('accounts', '0021_alter_conversation_classroom'),
        ('assignments', '0008_alter_assignment_classroom_alter_quiz_classroom'),
        ('attendance', '0010_alter_attendancerecord_classroom_and_more'),
        ('cameras', '0022_alter_camerarecording_classroom_and_more'),
        ('rag_workspace', '0004_alter_raginstructorsetting_classroom_and_more'),
        ('library', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel('MaterialBookmark'),
                migrations.DeleteModel('MaterialChunk'),
                migrations.DeleteModel('StudyMaterial'),
                migrations.DeleteModel('MaterialUnit'),
                migrations.DeleteModel('ClassroomMembership'),
                migrations.DeleteModel('Classroom'),
            ],
            database_operations=[]
        ),
    ]
