import os
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse


def project_upload_path(instance, filename):
    """Store uploads under media/videos/<user_id>/<uuid>_<filename>."""
    ext = os.path.splitext(filename)[1]
    new_name = f"{uuid.uuid4().hex}{ext}"
    
    if hasattr(instance, 'owner_id'):
        owner_id = instance.owner_id
    else:
        owner_id = instance.project.owner_id
        
    return f"videos/{owner_id}/{new_name}"


def _format_display_duration(duration_seconds):
    """Format duration in seconds into H:MM:SS.ms or M:SS.ms string."""
    if not duration_seconds:
        return ""
    secs = duration_seconds
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    ms = int(round((secs % 1) * 10))
    if h > 0:
        time_str = f"{h}:{m:02d}:{s:02d}"
    else:
        time_str = f"{m}:{s:02d}"
    if ms > 0:
        time_str += f".{ms}"
    return time_str


class VideoProject(models.Model):
    """
    A VideoProject wraps a single working video plus its metadata.
    Every edit operation (trim, mute, overlay, merge, ...) produces a new
    'current_file' and is logged as an EditOperation, so users can see a
    history of what happened. This keeps editing simple: each action re-runs
    ffmpeg on the current state and replaces it, rather than modeling a
    full non-destructive timeline.
    """

    STATUS_CHOICES = [
        ("ready", "Ready"),
        ("processing", "Processing"),
        ("error", "Error"),
    ]

    PROXY_STATUS_CHOICES = [
        ("none", "None"),
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=255, blank=True, default="")

    # The original file the user uploaded - never modified, kept for reference.
    original_file = models.FileField(upload_to=project_upload_path)

    # The current working file - this is what gets edited/replaced each operation.
    current_file = models.FileField(upload_to=project_upload_path, blank=True, null=True)

    duration_seconds = models.FloatField(blank=True, null=True)
    width = models.IntegerField(blank=True, null=True)
    height = models.IntegerField(blank=True, null=True)
    has_audio = models.BooleanField(default=True)
    trim_start = models.FloatField(default=0.0)
    trim_end = models.FloatField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ready")
    error_message = models.TextField(blank=True, default="")
    
    proxy_status = models.CharField(max_length=20, choices=PROXY_STATUS_CHOICES, default="none")
    proxy_url = models.CharField(max_length=500, blank=True, null=True)
    
    # JSON state of the timeline (clips, tracks, splits, overlays)
    timeline_state = models.JSONField(blank=True, null=True)

    @property
    def clips_json(self):
        """
        Backward-compatible property returning JSON string of timeline clips from timeline_state.
        Eliminates duplicate database state storage while preserving API compatibility.
        """
        import json
        if self.timeline_state and isinstance(self.timeline_state, dict):
            clips = self.timeline_state.get('clips') or self.timeline_state.get('video_clips')
            if not clips and 'tracks' in self.timeline_state:
                for t in self.timeline_state.get('tracks', []):
                    if isinstance(t, dict) and t.get('type') == 'video':
                        clips = t.get('clips', [])
                        break
            if clips:
                return json.dumps(clips)
        return "[]"

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["owner", "-updated_at"]),
            models.Index(fields=["status"]),
        ]

    @property
    def display_title(self):
        import re
        cleaned_title = self.title.strip()
        if cleaned_title and cleaned_title != "Untitled Project":
            if re.match(r'^[a-f0-9]{32}$', cleaned_title):
                return "Video Project"
            return cleaned_title
        if self.original_file:
            orig_name = os.path.basename(self.original_file.name)
            name_without_ext = os.path.splitext(orig_name)[0]
            if re.match(r'^[a-f0-9]{32}$', name_without_ext):
                return "Video Project"
            return orig_name
        return "Untitled Project"

    def __str__(self):
        return f"{self.display_title} ({self.owner})"

    def get_absolute_url(self):
        return reverse("project_detail", kwargs={"pk": self.pk})

    @property
    def display_duration(self):
        return _format_display_duration(self.duration_seconds)

    @property
    def exported_file(self):
        """The rendered export artifact if available, otherwise None."""
        return self.current_file if (self.current_file and self.current_file.name) else None

    @property
    def has_unexported_edits(self):
        """
        Returns True if:
        1. An export is currently processing.
        2. The project has never been exported, but has active timeline edits.
        3. The project was exported previously, but newer edit operations
           were logged after the last export.
        """
        if self.status == "processing":
            return True

        last_export = self.operations.filter(operation_type="timeline_export", active=True).order_by("-created_at").first()

        if not self.exported_file or not last_export:
            return self._has_timeline_edits()

        # Check if newer edit operations occurred after the last export
        return self.operations.filter(
            created_at__gt=last_export.created_at,
            active=True
        ).exclude(operation_type="timeline_export").exists()

    def _has_timeline_edits(self):
        """
        Returns True if timeline_state or operations indicate non-default edits.
        """
        state = self.timeline_state
        if not state or not isinstance(state, dict):
            return self.operations.exclude(operation_type__in=["upload", "timeline_export"]).filter(active=True).exists()

        dur = float(self.duration_seconds or 0.0)

        # Check trim
        trim = state.get("trim") or {}
        start = float(trim.get("start", 0.0) or 0.0)
        end = float(trim.get("end", dur) or dur)
        if start > 0.05 or (dur > 0 and end < dur - 0.05) or trim.get("fade_in") or trim.get("fade_out"):
            return True

        # Check speed
        if abs(float(state.get("speed", 1.0) or 1.0) - 1.0) > 0.01:
            return True

        # Check audio
        audio = state.get("audio") or {}
        if abs(float(audio.get("volume", 1.0) or 1.0) - 1.0) > 0.01:
            return True
        if audio.get("muted") and self.has_audio:
            return True

        # Check text overlays
        if state.get("text_overlays"):
            return True

        # Check background audios
        if state.get("background_audios"):
            return True

        # Check effects
        effects = state.get("effects") or {}
        if effects.get("grayscale") or (effects.get("rotate", 0) not in (0, 360, -360, "0", None)) or effects.get("fade"):
            return True

        # Check resize
        if state.get("resize"):
            return True

        # Check clips sequence
        clips = state.get("clips") or []
        if len(clips) > 1:
            return True
        elif len(clips) == 1:
            c = clips[0]
            c_dur = float(c.get("duration", dur) or dur)
            c_cut_start = float(c.get("cut_start", 0.0) or 0.0)
            c_cut_end = float(c.get("cut_end", c_dur) or c_dur)
            if c_cut_start > 0.05 or (c_dur > 0 and c_cut_end < c_dur - 0.05):
                return True
            if abs(float(c.get("speed", 1.0) or 1.0) - 1.0) > 0.01:
                return True
            if c.get("muted") and self.has_audio:
                return True
            if abs(float(c.get("volume", 1.0) or 1.0) - 1.0) > 0.01:
                return True
            if c.get("filter"):
                return True

        return self.operations.exclude(operation_type__in=["upload", "timeline_export"]).filter(active=True).exists()

    @property
    def working_file(self):
        """The rendered export file if available, otherwise original uploaded file."""
        return self.current_file if self.current_file else self.original_file

    @property
    def working_file_url(self):
        """Safely get working file URL without throwing exceptions when file is empty."""
        try:
            if self.current_file and hasattr(self.current_file, 'name') and self.current_file.name:
                return self.current_file.url
            if self.original_file and hasattr(self.original_file, 'name') and self.original_file.name:
                return self.original_file.url
        except Exception:
            pass
        return ""


class ProjectAsset(models.Model):
    """
    Holds extra audio, video, or image files uploaded to a project for multi-track editing.
    """
    ASSET_TYPES = [
        ("video", "Video"),
        ("audio", "Audio"),
        ("image", "Image"),
    ]
    project = models.ForeignKey(VideoProject, on_delete=models.CASCADE, related_name="assets")
    asset_type = models.CharField(max_length=10, choices=ASSET_TYPES, default="video")
    file = models.FileField(upload_to=project_upload_path)
    filename = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=255, blank=True, default="")
    duration_seconds = models.FloatField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["project", "-updated_at"]),
        ]

    @property
    def display_title(self):
        return self.title or self.filename or os.path.basename(self.file.name)

    def __str__(self):
        return f"{self.display_title} ({self.get_asset_type_display()})"

    def get_absolute_url(self):
        return self.file.url

    @property
    def display_duration(self):
        return _format_display_duration(self.duration_seconds)


class EditOperation(models.Model):
    """A single logged edit action, for display in the project history panel."""

    OPERATION_CHOICES = [
        ("upload", "Uploaded"),
        ("trim", "Trimmed / Cut"),
        ("mute", "Muted Audio"),
        ("unmute", "Unmuted Audio"),
        ("volume", "Adjusted Volume"),
        ("merge", "Merged Clip"),
        ("text_overlay", "Added Text Overlay"),
        ("speed", "Changed Speed"),
        ("rotate", "Rotated"),
        ("resize", "Resized"),
        ("grayscale", "Applied Grayscale"),
        ("fade", "Applied Fade"),
        ("reset", "Reset to Original"),
    ]

    project = models.ForeignKey(VideoProject, on_delete=models.CASCADE, related_name="operations")
    operation_type = models.CharField(max_length=30, choices=OPERATION_CHOICES)
    description = models.CharField(max_length=500, blank=True, default="")

    # Undo/redo flag — False means this operation has been undone
    active = models.BooleanField(default=True)

    # Optional snapshot of the result file and a secondary resource (e.g. merge clip)
    video_file = models.FileField(upload_to=project_upload_path, blank=True, null=True)
    resource_file = models.FileField(upload_to=project_upload_path, blank=True, null=True)

    # Optional JSON bag of operation parameters for display / replay
    parameters = models.JSONField(blank=True, null=True)

    # Trim state at the time of this operation
    trim_start = models.FloatField(default=0.0)
    trim_end = models.FloatField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "active", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.get_operation_type_display()} on {self.project.title}"

