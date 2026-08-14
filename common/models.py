"""
Common model mixins used across all apps
"""
from django.db import models
from django.utils import timezone


class TimestampMixin(models.Model):
    """
    Adds created_at and updated_at fields to any model
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


class SoftDeleteMixin(models.Model):
    """
    Adds soft delete functionality to models
    """
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at'])


class ActiveStatusMixin(models.Model):
    """
    Adds is_active field for easy active/inactive toggling
    """
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True
