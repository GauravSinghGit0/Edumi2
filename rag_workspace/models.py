from django.db import models
from django.contrib.auth import get_user_model
from meetings.models import Classroom, StudyMaterial

User = get_user_model()


class RagSession(models.Model):
    """Represents a dedicated AI Study Workspace session for a user."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rag_sessions')
    classroom = models.ForeignKey(Classroom, on_delete=models.SET_NULL, null=True, blank=True, related_name='rag_sessions')
    title = models.CharField(max_length=255, default="AI Study Session")
    selected_materials = models.ManyToManyField(StudyMaterial, related_name='rag_sessions', blank=True)
    strict_mode = models.BooleanField(default=True)
    active_mode = models.CharField(max_length=50, default='ask')  # ask, explain, summarize, quiz, revision
    explain_level = models.CharField(max_length=30, default='detailed')  # simple, detailed, exam
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'RAG Study Session'
        verbose_name_plural = 'RAG Study Sessions'

    def __str__(self):
        return f"{self.user.username} - {self.title} ({self.created_at.strftime('%b %d')})"


class RagQueryLog(models.Model):
    """Logs prompts, RAG context retrieval, source citations, and LLM responses."""
    session = models.ForeignKey(RagSession, on_delete=models.CASCADE, related_name='query_logs', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rag_query_logs')
    mode = models.CharField(max_length=30, default='ask')
    prompt = models.TextField()
    response = models.TextField()
    retrieved_chunks_count = models.IntegerField(default=0)
    sources_cited = models.JSONField(default=list, blank=True)
    strict_mode_applied = models.BooleanField(default=True)
    not_found = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'RAG Query Log'
        verbose_name_plural = 'RAG Query Logs'

    def __str__(self):
        return f"Query [{self.mode}] by {self.user.username} @ {self.created_at.strftime('%H:%M')}"


class RagChatMessage(models.Model):
    """Stores individual chat turn messages within a user's RAG study session."""
    session = models.ForeignKey(RagSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=[('user', 'User'), ('assistant', 'Assistant'), ('system', 'System')])
    content = models.TextField()
    sources = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'RAG Chat Message'
        verbose_name_plural = 'RAG Chat Messages'

    def __str__(self):
        return f"{self.role.title()} message in {self.session.title} @ {self.created_at.strftime('%H:%M')}"


class RagInstructorSetting(models.Model):
    """Course-level instructor controls for AI Study Workspace features."""
    classroom = models.OneToOneField(Classroom, on_delete=models.CASCADE, related_name='rag_setting')
    allow_questions = models.BooleanField(default=True)
    allow_summaries = models.BooleanField(default=True)
    allow_quiz = models.BooleanField(default=True)
    allow_revision = models.BooleanField(default=True)
    show_citations = models.BooleanField(default=True)
    allow_change_scope = models.BooleanField(default=True)
    allow_outside_knowledge = models.BooleanField(default=False)
    strict_material_mode = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AI Settings - {self.classroom.title}"

