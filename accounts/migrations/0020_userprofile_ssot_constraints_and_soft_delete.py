"""
accounts/migrations/0020_userprofile_ssot_constraints_and_soft_delete.py

Schema migration:
- Removes redundant contact_number and roll_number columns (now handled via property aliases)
- Adds SoftDeleteMixin columns (is_deleted, deleted_at)
- Adds unique constraints on student_id and employee_id (non-empty)
- Adds case-insensitive unique email index on auth_user (vendor-aware)
"""

from django.db import migrations, models


def create_email_unique_index(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == 'postgresql':
        schema_editor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS auth_user_email_unique_idx ON auth_user (LOWER(email)) WHERE email IS NOT NULL AND email != '';"
        )
    elif vendor == 'sqlite':
        schema_editor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS auth_user_email_unique_idx ON auth_user (email COLLATE NOCASE) WHERE email IS NOT NULL AND email != '';"
        )


def drop_email_unique_index(apps, schema_editor):
    schema_editor.execute("DROP INDEX IF EXISTS auth_user_email_unique_idx;")


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0019_consolidate_profile_fields_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userprofile',
            name='contact_number',
        ),
        migrations.RemoveField(
            model_name='userprofile',
            name='roll_number',
        ),
        migrations.AddField(
            model_name='userprofile',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='is_deleted',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='employee_id',
            field=models.CharField(blank=True, db_index=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='student_id',
            field=models.CharField(blank=True, db_index=True, max_length=50, null=True, verbose_name='Student / Roll ID'),
        ),
        migrations.AddConstraint(
            model_name='userprofile',
            constraint=models.UniqueConstraint(condition=models.Q(('student_id__isnull', False), models.Q(('student_id', ''), _negated=True)), fields=('student_id',), name='unique_student_id_non_empty'),
        ),
        migrations.AddConstraint(
            model_name='userprofile',
            constraint=models.UniqueConstraint(condition=models.Q(('employee_id__isnull', False), models.Q(('employee_id', ''), _negated=True)), fields=('employee_id',), name='unique_employee_id_non_empty'),
        ),
        migrations.RunPython(
            create_email_unique_index,
            reverse_code=drop_email_unique_index
        ),
    ]
