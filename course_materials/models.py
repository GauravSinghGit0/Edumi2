from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

def study_material_upload_path(instance, filename):
    """Store material under classroom directory"""
    return f"study_materials/{instance.classroom_id}/{filename}"


class MaterialUnit(models.Model):
    """
    Curriculum unit or topic folder.
    MIGRATED from meetings.models.MaterialUnit in Phase 1B.
    """
    classroom = models.ForeignKey(
        'academics.Classroom',
        on_delete=models.CASCADE,
        related_name='material_units'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meetings_materialunit'  # CRITICAL: Reuse existing table
        ordering = ['order', 'created_at']
        verbose_name = 'Material Unit'
        verbose_name_plural = 'Material Units'

    def __str__(self):
        return f"{self.classroom.title} - {self.title}"

    def get_published_materials(self):
        return self.materials.filter(is_published=True).order_by('-created_at')


class StudyMaterial(models.Model):
    """
    Digital study resource with RAG support.
    MIGRATED from meetings.models.StudyMaterial in Phase 1B.
    """
    MATERIAL_TYPES = [
        ('document', 'Document / PDF / Word'),
        ('slides', 'Presentation / Slides'),
        ('notes', 'Lecture Notes / Markdown'),
        ('video', 'Video / Lecture Recording'),
        ('link', 'External Web Link / Resource'),
        ('book', 'e-Book / Reference Book'),
    ]

    classroom = models.ForeignKey(
        'academics.Classroom',
        on_delete=models.CASCADE,
        related_name='study_materials'
    )
    unit = models.ForeignKey(
        MaterialUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='materials'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    material_type = models.CharField(max_length=20, choices=MATERIAL_TYPES, default='document')
    file = models.FileField(upload_to=study_material_upload_path, null=True, blank=True)
    external_url = models.URLField(max_length=500, blank=True, null=True)
    content_text = models.TextField(blank=True, help_text="Rich text / markdown notes content")
    file_size_bytes = models.BigIntegerField(default=0)
    file_extension = models.CharField(max_length=20, blank=True)
    is_published = models.BooleanField(default=True, db_index=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_materials')
    download_count = models.IntegerField(default=0)
    view_count = models.IntegerField(default=0)

    # RAG (Retrieval-Augmented Generation) fields
    extracted_text = models.TextField(blank=True, help_text="Parsed plaintext for LLM/RAG search indexing")
    summary_ai = models.TextField(blank=True, help_text="AI-generated conceptual summary")
    key_topics = models.JSONField(default=list, blank=True, help_text="Extracted keywords/topics for hybrid search")
    rag_indexed = models.BooleanField(default=False, db_index=True, help_text="True if document chunks are embedded in vector store")
    rag_indexed_at = models.DateTimeField(null=True, blank=True)
    rag_metadata = models.JSONField(default=dict, blank=True, help_text="Vector IDs, model version & chunking metadata")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meetings_studymaterial'  # CRITICAL: Reuse existing table
        ordering = ['-created_at']
        verbose_name = 'Study Material'
        verbose_name_plural = 'Study Materials'

    def __str__(self):
        return f"{self.title} ({self.get_material_type_display()})"

    def get_file_size_formatted(self):
        """Format byte count"""
        bytes_val = self.file_size_bytes or (self.file.size if self.file else 0)
        if not bytes_val:
            return ""
        if bytes_val < 1024:
            return f"{bytes_val} B"
        elif bytes_val < 1024 * 1024:
            return f"{bytes_val / 1024:.1f} KB"
        elif bytes_val < 1024 * 1024 * 1024:
            return f"{bytes_val / (1024 * 1024):.1f} MB"
        return f"{bytes_val / (1024 * 1024 * 1024):.1f} GB"

    def get_icon_name(self):
        icons = {
            'document': 'file-text',
            'slides': 'presentation',
            'notes': 'book-open',
            'video': 'video',
            'link': 'external-link',
            'book': 'bookmark',
        }
        return icons.get(self.material_type, 'file')

    def get_badge_color(self):
        colors = {
            'document': '#ef4444',
            'slides': '#f59e0b',
            'notes': '#3b82f6',
            'video': '#8b5cf6',
            'link': '#10b981',
            'book': '#6366f1',
        }
        return colors.get(self.material_type, '#64748b')

    def is_bookmarked_by(self, user):
        if not user or not user.is_authenticated:
            return False
        return self.bookmarks.filter(user=user).exists()


class MaterialChunk(models.Model):
    """
    Segmented text chunk for RAG embedding.
    MIGRATED from meetings.models.MaterialChunk in Phase 1B.
    """
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.IntegerField(default=0)
    chunk_text = models.TextField()
    token_count = models.IntegerField(default=0)
    page_number = models.IntegerField(null=True, blank=True)
    embedding_id = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    embedding_vector = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'meetings_materialchunk'  # CRITICAL: Reuse existing table
        ordering = ['material', 'chunk_index']
        verbose_name = 'Material Chunk'
        verbose_name_plural = 'Material Chunks'

    def __str__(self):
        return f"{self.material.title} [Chunk #{self.chunk_index}]"


class MaterialBookmark(models.Model):
    """
    User bookmark for quick library access.
    MIGRATED from meetings.models.MaterialBookmark in Phase 1B.
    """
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE, related_name='bookmarks')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='material_bookmarks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'meetings_materialbookmark'  # CRITICAL: Reuse existing table
        unique_together = ['material', 'user']
        ordering = ['-created_at']

