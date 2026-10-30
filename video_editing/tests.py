import os
import shutil
import subprocess
import tempfile
import threading
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from video_editing.models import VideoProject
from video_editing.timeline_compiler import compile_timeline_to_ffmpeg


# ---------------------------------------------------------------------------
# Step 1: Drawtext special characters and emoji handling
# ---------------------------------------------------------------------------
class TimelineCompilerDrawtextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.test_dir = os.path.join(settings.MEDIA_ROOT, "test_drawtext_media")
        os.makedirs(cls.test_dir, exist_ok=True)
        cls.sample_video_path = os.path.join(cls.test_dir, "sample.mp4")

        # Generate 1-second test video with audio
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=1",
            "-c:v", "libx264", "-c:a", "aac",
            cls.sample_video_path
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="drawtextuser", password="pw", email="dt@test.com"
        )

    def test_drawtext_special_characters_and_emoji(self):
        """Drawtext overlay with ', ;, ,, :, %, \\, [, ], newline and emoji succeeds."""
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Special Chars Drawtext",
            original_file="test_drawtext_media/sample.mp4",
            current_file="test_drawtext_media/sample.mp4",
        )

        nasty_text = "' ; , : % \\ [ ] \n newline 🎓 🎬!"
        timeline_data = {
            "clips": [
                {
                    "title": "Clip1",
                    "path": self.sample_video_path,
                    "start": 0.0,
                    "end": 1.0,
                    "trimStart": 0.0,
                    "trimEnd": 1.0,
                }
            ],
            "text_overlays": [
                {
                    "text": nasty_text,
                    "start": 0.0,
                    "end": 1.0,
                    "x": 10,
                    "y": 10,
                    "fontsize": 24,
                    "fontcolor": "white",
                }
            ]
        }

        output_path = os.path.join(self.test_dir, "drawtext_out.mp4")
        compile_timeline_to_ffmpeg(proj, timeline_data, output_path)

        self.assertTrue(os.path.exists(output_path), f"Output was not generated: {output_path}")
        self.assertGreater(os.path.getsize(output_path), 0, "Output file is empty")


# ---------------------------------------------------------------------------
# Step 2: export_project never blocks; stale reconciliation
# ---------------------------------------------------------------------------
class ExportThreadingTests(TestCase):
    """export_project must never call export_video_task synchronously."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="exportuser2", password="pw", email="eu2@test.com"
        )
        self.client.force_login(self.user)

    def _make_project(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Thread Test",
            original_file=tmp.name,
            current_file=tmp.name,
            status="ready",
        )
        return proj, tmp.name

    def test_offline_celery_spawns_thread_not_sync(self):
        """When Celery inspect returns None the task must run in a daemon thread."""
        proj, tmp = self._make_project()
        spawned = []

        original_thread_init = threading.Thread.__init__

        def capturing_init(self_t, *args, **kwargs):
            original_thread_init(self_t, *args, **kwargs)
            spawned.append(self_t)

        payload = b'{"clips": []}'

        with patch("school_project.celery.app.control.inspect") as mock_inspect, \
             patch("video_editing.tasks.export_video_task") as mock_task, \
             patch.object(threading.Thread, "__init__", capturing_init), \
             patch.object(threading.Thread, "start", lambda s: None):
            mock_inspect.return_value.stats.return_value = None
            response = self.client.post(
                reverse("export_project", args=[proj.pk]),
                data=payload,
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(resp_data["status"], "success")
        mock_task.assert_not_called()
        self.assertGreater(len(spawned), 0, "No Thread was spawned")
        os.unlink(tmp)

    def test_celery_exception_spawns_thread_not_sync(self):
        """When Celery import/inspect raises, task must still run in a thread."""
        proj, tmp = self._make_project()
        spawned = []

        original_thread_init = threading.Thread.__init__

        def capturing_init(self_t, *args, **kwargs):
            original_thread_init(self_t, *args, **kwargs)
            spawned.append(self_t)

        payload = b'{"clips": []}'

        with patch("school_project.celery.app.control.inspect", side_effect=Exception("celery down")), \
             patch("video_editing.tasks.export_video_task") as mock_task, \
             patch.object(threading.Thread, "__init__", capturing_init), \
             patch.object(threading.Thread, "start", lambda s: None):
            response = self.client.post(
                reverse("export_project", args=[proj.pk]),
                data=payload,
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        mock_task.assert_not_called()
        self.assertGreater(len(spawned), 0, "No Thread was spawned on Celery exception")
        os.unlink(tmp)


class StaleReconcileTests(TestCase):
    """_reconcile_stale_exports marks old processing projects as error."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="reconcileuser", password="pw", email="rc@test.com"
        )

    def _make_stale_project(self, minutes_old=60):
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Stale",
            original_file=tmp.name,
            current_file=tmp.name,
            status="processing",
        )
        VideoProject.objects.filter(pk=proj.pk).update(
            updated_at=timezone.now() - timedelta(minutes=minutes_old)
        )
        os.unlink(tmp.name)
        return VideoProject.objects.get(pk=proj.pk)

    def test_stale_project_becomes_error(self):
        from video_editing.apps import _reconcile_stale_exports
        proj = self._make_stale_project(minutes_old=60)
        _reconcile_stale_exports(sender=None)
        proj.refresh_from_db()
        self.assertEqual(proj.status, "error")
        self.assertIn("interrupted", proj.error_message)

    def test_recent_processing_not_touched(self):
        """A project only 5 minutes old must NOT be reconciled."""
        from video_editing.apps import _reconcile_stale_exports
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Fresh",
            original_file=tmp.name,
            current_file=tmp.name,
            status="processing",
        )
        _reconcile_stale_exports(sender=None)
        proj.refresh_from_db()
        self.assertEqual(proj.status, "processing")
        os.unlink(tmp.name)
        proj.delete()


# ---------------------------------------------------------------------------
# Step 3: Audio sample rate and channel layout normalization
# ---------------------------------------------------------------------------
class AudioNormalizationTests(TestCase):
    """Real and background audio streams must be normalized to 44.1kHz stereo before concat/amix."""

    @classmethod
    def setUpTestData(cls):
        cls.test_dir = os.path.join(settings.MEDIA_ROOT, "test_audio_norm")
        os.makedirs(cls.test_dir, exist_ok=True)

        cls.clip_44k = os.path.join(cls.test_dir, "clip_44k.mp4")
        cls.clip_48k_mono = os.path.join(cls.test_dir, "clip_48k_mono.mp4")
        cls.clip_no_audio = os.path.join(cls.test_dir, "clip_no_audio.mp4")
        cls.bg_audio = os.path.join(cls.test_dir, "bg_audio.mp3")

        # 44.1kHz stereo video clip
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=1",
            "-c:v", "libx264", "-c:a", "aac", "-ac", "2", "-ar", "44100",
            cls.clip_44k
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # 48kHz mono video clip
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=1",
            "-c:v", "libx264", "-c:a", "aac", "-ac", "1", "-ar", "48000",
            cls.clip_48k_mono
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Video clip with NO audio
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
            "-an", "-c:v", "libx264",
            cls.clip_no_audio
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # 22.05kHz mono background audio
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=22050:duration=1",
            "-c:a", "mp3", "-ac", "1", "-ar", "22050",
            cls.bg_audio
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="audiouser", password="pw", email="au@test.com"
        )

    def test_concat_mixed_audio_sample_rates_and_channels(self):
        """Concatenating 44.1kHz stereo and 48kHz mono clips succeeds without audio filter mismatch."""
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Mixed Audio Project",
            original_file="test_audio_norm/clip_44k.mp4",
            current_file="test_audio_norm/clip_44k.mp4",
        )

        timeline_data = {
            "clips": [
                {
                    "title": "Clip44k",
                    "path": self.clip_44k,
                    "start": 0.0,
                    "end": 1.0,
                    "trimStart": 0.0,
                    "trimEnd": 1.0,
                },
                {
                    "title": "Clip48kMono",
                    "path": self.clip_48k_mono,
                    "start": 1.0,
                    "end": 2.0,
                    "trimStart": 0.0,
                    "trimEnd": 1.0,
                },
            ]
        }

        output_path = os.path.join(self.test_dir, "out_mixed_audio.mp4")
        compile_timeline_to_ffmpeg(proj, timeline_data, output_path)

        self.assertTrue(os.path.exists(output_path), f"Output file was not created: {output_path}")
        self.assertGreater(os.path.getsize(output_path), 0, "Output file is empty")

    def test_concat_audio_clip_and_silent_clip(self):
        """Concatenating a clip with audio and a clip with no audio stream succeeds."""
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Audio + Silent Project",
            original_file="test_audio_norm/clip_44k.mp4",
            current_file="test_audio_norm/clip_44k.mp4",
        )

        timeline_data = {
            "clips": [
                {
                    "title": "ClipWithAudio",
                    "path": self.clip_44k,
                    "start": 0.0,
                    "end": 1.0,
                    "trimStart": 0.0,
                    "trimEnd": 1.0,
                },
                {
                    "title": "ClipSilent",
                    "path": self.clip_no_audio,
                    "start": 1.0,
                    "end": 2.0,
                    "trimStart": 0.0,
                    "trimEnd": 1.0,
                },
            ]
        }

        output_path = os.path.join(self.test_dir, "out_audio_silent.mp4")
        compile_timeline_to_ffmpeg(proj, timeline_data, output_path)

        self.assertTrue(os.path.exists(output_path), f"Output file was not created: {output_path}")
        self.assertGreater(os.path.getsize(output_path), 0, "Output file is empty")

    def test_background_audio_different_sample_rate(self):
        """Mixing 22.05kHz mono background audio into a 48kHz project succeeds."""
        proj = VideoProject.objects.create(
            owner=self.user,
            title="BG Audio Project",
            original_file="test_audio_norm/clip_48k_mono.mp4",
            current_file="test_audio_norm/clip_48k_mono.mp4",
        )

        timeline_data = {
            "clips": [
                {
                    "title": "Clip48k",
                    "path": self.clip_48k_mono,
                    "start": 0.0,
                    "end": 1.0,
                    "trimStart": 0.0,
                    "trimEnd": 1.0,
                }
            ],
            "audioClips": [
                {
                    "title": "BgAudio",
                    "path": self.bg_audio,
                    "start": 0.0,
                    "end": 1.0,
                    "trimStart": 0.0,
                    "trimEnd": 1.0,
                    "volume": 0.8,
                }
            ]
        }

        output_path = os.path.join(self.test_dir, "out_bg_audio.mp4")
        compile_timeline_to_ffmpeg(proj, timeline_data, output_path)

        self.assertTrue(os.path.exists(output_path), f"Output file was not created: {output_path}")
        self.assertGreater(os.path.getsize(output_path), 0, "Output file is empty")


# ---------------------------------------------------------------------------
# Step 4: project_delete & _apply_new_working_file proxy and asset cleanup
# ---------------------------------------------------------------------------
from video_editing.models import ProjectAsset
from video_editing.views import _apply_new_working_file


class ProjectCleanupTests(TestCase):
    """Deleting a project or applying a new working file must thoroughly clean disk files."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="cleanupuser", password="pw", email="cu@test.com"
        )
        self.client.force_login(self.user)

    def test_project_delete_removes_proxies_assets_tmp_audio(self):
        """project_delete removes proxy dir, asset files, and tmp audio from disk."""
        # 1. Create a dummy original video inside MEDIA_ROOT
        orig_rel = "test_cleanup/orig.mp4"
        orig_full = os.path.join(settings.MEDIA_ROOT, "test_cleanup", "orig.mp4")
        os.makedirs(os.path.dirname(orig_full), exist_ok=True)
        with open(orig_full, "wb") as f:
            f.write(b"dummy original video content")

        proj = VideoProject.objects.create(
            owner=self.user,
            title="To Delete",
            original_file=orig_rel,
            current_file=orig_rel,
        )

        # 2. Create proxy dir with dummy files
        proxy_dir = os.path.join(settings.MEDIA_ROOT, "proxies", str(proj.owner_id), str(proj.pk))
        os.makedirs(proxy_dir, exist_ok=True)
        proxy_file = os.path.join(proxy_dir, "proxy.mp4")
        with open(proxy_file, "wb") as f:
            f.write(b"dummy proxy content")

        # 3. Create ProjectAsset with real file
        asset_rel = f"test_cleanup/asset_{proj.pk}.mp4"
        asset_full = os.path.join(settings.MEDIA_ROOT, asset_rel)
        with open(asset_full, "wb") as f:
            f.write(b"dummy asset content")
        asset_obj = ProjectAsset.objects.create(
            project=proj,
            asset_type="video",
            file=asset_rel,
            filename="asset.mp4",
        )

        # 4. Create tmp audio file
        tmp_dir = os.path.join(settings.MEDIA_ROOT, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_audio_path = os.path.join(tmp_dir, f"audio_cleanuptest_{proj.pk}.mp3")
        with open(tmp_audio_path, "wb") as f:
            f.write(b"dummy tmp audio")

        proj.timeline_state = {
            "audioClips": [
                {"temp_path": tmp_audio_path}
            ]
        }
        proj.save(update_fields=["timeline_state"])

        # Pre-assertions
        self.assertTrue(os.path.exists(proxy_dir))
        self.assertTrue(os.path.exists(asset_full))
        self.assertTrue(os.path.exists(tmp_audio_path))

        # Perform deletion via view
        resp = self.client.post(reverse("project_delete", args=[proj.pk]))
        self.assertEqual(resp.status_code, 302)

        # Post-assertions: all files and dirs removed from disk
        self.assertFalse(os.path.exists(proxy_dir), "Proxy directory was not deleted")
        self.assertFalse(os.path.exists(asset_full), "Project asset file was not deleted")
        self.assertFalse(os.path.exists(tmp_audio_path), "Temp audio file was not deleted")
        self.assertFalse(VideoProject.objects.filter(pk=proj.pk).exists(), "Project still exists in DB")

        # Clean test container folder
        shutil.rmtree(os.path.join(settings.MEDIA_ROOT, "test_cleanup"), ignore_errors=True)

    def test_apply_new_working_file_clears_old_proxies(self):
        """_apply_new_working_file deletes existing proxy dir and resets proxy fields."""
        # Generate a real 1-second video for ffmpeg_utils.get_metadata to inspect
        tmp_work = os.path.join(settings.MEDIA_ROOT, "tmp_work_test.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=1",
            "-c:v", "libx264", "-c:a", "aac",
            tmp_work
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        proj = VideoProject.objects.create(
            owner=self.user,
            title="Working File Test",
            original_file="tmp_work_test.mp4",
            current_file="tmp_work_test.mp4",
            proxy_url="http://example.com/proxy.m3u8",
            proxy_status="ready",
        )

        proxy_dir = os.path.join(settings.MEDIA_ROOT, "proxies", str(proj.owner_id), str(proj.pk))
        os.makedirs(proxy_dir, exist_ok=True)
        with open(os.path.join(proxy_dir, "waveform.json"), "w") as f:
            f.write("{}")

        self.assertTrue(os.path.exists(proxy_dir))

        # Make another copy as the temp output of an operation
        tmp_op_output = os.path.join(settings.MEDIA_ROOT, "tmp_op_out.mp4")
        shutil.copyfile(tmp_work, tmp_op_output)

        _apply_new_working_file(proj, tmp_op_output, "trim", "Trimmed video")

        self.assertFalse(os.path.exists(proxy_dir), "Old proxy directory was not removed on working file update")
        proj.refresh_from_db()
        self.assertEqual(proj.proxy_url, "", "proxy_url was not cleared")
        self.assertEqual(proj.proxy_status, "none", "proxy_status was not reset to 'none'")

        # Clean up
        if os.path.exists(tmp_work):
            os.remove(tmp_work)
        if proj.current_file and os.path.exists(proj.current_file.path):
            try:
                os.remove(proj.current_file.path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Step 5: Export task lifecycle, failure reporting, and error cleanup
# ---------------------------------------------------------------------------
from video_editing.tasks import export_video_task


class ExportTaskLifecycleTests(TestCase):
    """export_video_task must correctly mark project status as ready on success or error on failure."""

    @classmethod
    def setUpTestData(cls):
        cls.test_dir = os.path.join(settings.MEDIA_ROOT, "test_task_lifecycle")
        os.makedirs(cls.test_dir, exist_ok=True)

        cls.valid_vid = os.path.join(cls.test_dir, "valid.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=1",
            "-c:v", "libx264", "-c:a", "aac",
            cls.valid_vid
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        cls.corrupt_vid = os.path.join(cls.test_dir, "corrupt.mp4")
        with open(cls.corrupt_vid, "wb") as f:
            f.write(b"this is corrupt non-media data")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="lifecycler", password="pw", email="lc@test.com"
        )

    def test_export_video_task_success_marks_ready(self):
        """Successful export_video_task updates status to 'ready' and saves current_file."""
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Lifecycle Success",
            original_file="test_task_lifecycle/valid.mp4",
            current_file="test_task_lifecycle/valid.mp4",
            status="processing",
        )

        timeline_data = {
            "clips": [
                {
                    "title": "Clip1",
                    "path": self.valid_vid,
                    "start": 0.0,
                    "end": 1.0,
                    "trimStart": 0.0,
                    "trimEnd": 1.0,
                }
            ]
        }

        export_video_task(proj.id, timeline_data)
        proj.refresh_from_db()

        self.assertEqual(proj.status, "ready")
        self.assertEqual(proj.error_message, "")
        self.assertTrue(proj.current_file)
        self.assertTrue(os.path.exists(proj.current_file.path))

    def test_export_video_task_failure_marks_error(self):
        """Failed export_video_task transitions status to 'error' and preserves error_message."""
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Lifecycle Failure",
            original_file="test_task_lifecycle/corrupt.mp4",
            current_file="test_task_lifecycle/corrupt.mp4",
            status="processing",
        )

        timeline_data = {
            "clips": [
                {
                    "title": "CorruptClip",
                    "path": self.corrupt_vid,
                    "start": 0.0,
                    "end": 1.0,
                    "trimStart": 0.0,
                    "trimEnd": 1.0,
                }
            ]
        }

        export_video_task(proj.id, timeline_data)
        proj.refresh_from_db()

        self.assertEqual(proj.status, "error")
        self.assertGreater(len(proj.error_message), 0)

    def test_export_video_task_preserves_source_proxies_and_duration(self):
        """export_video_task must NOT destroy source proxy cache or overwrite source duration."""
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Preserve Proxies",
            original_file="test_task_lifecycle/valid.mp4",
            current_file="test_task_lifecycle/valid.mp4",
            duration_seconds=60.0,
            width=1920,
            height=1080,
            proxy_url="/media/proxies/test/proxy.mp4",
            proxy_status="completed",
            status="processing",
        )

        proxy_dir = os.path.join(settings.MEDIA_ROOT, "proxies", str(proj.owner_id), str(proj.pk))
        os.makedirs(proxy_dir, exist_ok=True)
        dummy_proxy_file = os.path.join(proxy_dir, "proxy.mp4")
        with open(dummy_proxy_file, "wb") as f:
            f.write(b"dummy 360p proxy")

        timeline_data = {
            "clips": [
                {
                    "title": "Clip1",
                    "path": self.valid_vid,
                    "start": 0.0,
                    "end": 1.0,
                    "trimStart": 0.0,
                    "trimEnd": 1.0,
                }
            ]
        }

        export_video_task(proj.id, timeline_data)
        proj.refresh_from_db()

        # Export succeeded
        self.assertEqual(proj.status, "ready")
        self.assertTrue(proj.current_file)
        self.assertEqual(proj.exported_file, proj.current_file)

        # Source project metadata and proxies are preserved
        self.assertEqual(proj.duration_seconds, 60.0, "Source project duration was overwritten by export output")
        self.assertTrue(os.path.exists(proxy_dir), "Source proxy directory was deleted by export")
        self.assertTrue(os.path.exists(dummy_proxy_file), "Source proxy file was deleted by export")
        self.assertEqual(proj.proxy_status, "completed", "proxy_status was reset")
        self.assertEqual(proj.proxy_url, "/media/proxies/test/proxy.mp4", "proxy_url was cleared")

        # Clean proxy dir
        shutil.rmtree(proxy_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Step 2 Migration: Protect Download & Publish to Lecture against unexported edits
# ---------------------------------------------------------------------------
class DownloadAndPublishProtectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.test_dir = os.path.join(settings.MEDIA_ROOT, "test_step2_protection")
        os.makedirs(cls.test_dir, exist_ok=True)

        cls.sample_video_path = os.path.join(cls.test_dir, "sample.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=1",
            "-c:v", "libx264", "-c:a", "aac",
            cls.sample_video_path
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="step2user", password="password123", email="step2@example.com"
        )
        self.client.login(username="step2user", password="password123")

    def test_download_unmodified_project_succeeds(self):
        """A project without edits downloads original file directly."""
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Clean Project",
            original_file="test_step2_protection/sample.mp4",
            duration_seconds=1.0,
            status="ready",
        )
        res = self.client.get(reverse("project_download", args=[proj.id]))
        self.assertEqual(res.status_code, 200)

    def test_download_blocks_unexported_timeline_edits(self):
        """A project with unexported timeline edits redirects to detail with a warning message."""
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Edited Project",
            original_file="test_step2_protection/sample.mp4",
            duration_seconds=1.0,
            status="ready",
            timeline_state={
                "trim": {"start": 0.2, "end": 0.8},
                "speed": 1.0,
                "audio": {"volume": 1.0, "muted": False},
                "clips": [{"title": "sample.mp4", "duration": 1.0, "start": 0.0, "end": 1.0}]
            }
        )
        self.assertTrue(proj.has_unexported_edits)
        res = self.client.get(reverse("project_download", args=[proj.id]), follow=True)
        self.assertRedirects(res, reverse("project_detail", args=[proj.id]))
        messages = list(res.context["messages"])
        self.assertTrue(any("unexported timeline edits" in str(m) for m in messages))

    def test_download_blocks_while_processing(self):
        """A project currently rendering export redirects with a warning."""
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Processing Project",
            original_file="test_step2_protection/sample.mp4",
            duration_seconds=1.0,
            status="processing",
        )
        self.assertTrue(proj.has_unexported_edits)
        res = self.client.get(reverse("project_download", args=[proj.id]), follow=True)
        self.assertRedirects(res, reverse("project_detail", args=[proj.id]))
        messages = list(res.context["messages"])
        self.assertTrue(any("currently processing" in str(m) for m in messages))

    def test_download_exported_project_serves_exported_file(self):
        """Once exported, download serves the rendered export artifact."""
        from video_editing.models import EditOperation
        exported_path = os.path.join(self.test_dir, "export.mp4")
        shutil.copyfile(self.sample_video_path, exported_path)

        proj = VideoProject.objects.create(
            owner=self.user,
            title="Exported Project",
            original_file="test_step2_protection/sample.mp4",
            current_file="test_step2_protection/export.mp4",
            duration_seconds=1.0,
            status="ready",
        )
        EditOperation.objects.create(
            project=proj,
            operation_type="timeline_export",
            description="Exported JSON Timeline"
        )
        self.assertFalse(proj.has_unexported_edits)
        res = self.client.get(reverse("project_download", args=[proj.id]))
        self.assertEqual(res.status_code, 200)

    def test_publish_blocks_unexported_edits(self):
        """publish_to_lecture blocks when project has unexported edits."""
        from cameras.models import CameraRecording
        recording = CameraRecording.objects.create(
            teacher=self.user,
            title="Lecture 1",
            video_file="test_step2_protection/sample.mp4",
            is_published=False,
        )
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Edited Project",
            original_file="test_step2_protection/sample.mp4",
            duration_seconds=1.0,
            status="ready",
            timeline_state={
                "text_overlays": [{"text": "Hello", "start": 0.0, "end": 1.0}]
            }
        )
        self.assertTrue(proj.has_unexported_edits)
        url = reverse("publish_to_lecture", args=[proj.id]) + f"?recording_id={recording.id}"
        res = self.client.post(url, follow=True)
        self.assertRedirects(res, f"{reverse('project_detail', args=[proj.id])}?recording_id={recording.id}")
        recording.refresh_from_db()
        self.assertFalse(recording.is_published)
        messages = list(res.context["messages"])
        self.assertTrue(any("unexported timeline edits" in str(m) for m in messages))

    def test_publish_succeeds_when_exported(self):
        """publish_to_lecture succeeds and publishes when project has been exported."""
        from cameras.models import CameraRecording
        from video_editing.models import EditOperation

        recording = CameraRecording.objects.create(
            teacher=self.user,
            title="Lecture 2",
            video_file="test_step2_protection/sample.mp4",
            is_published=False,
        )
        exported_path = os.path.join(self.test_dir, "export2.mp4")
        shutil.copyfile(self.sample_video_path, exported_path)

        proj = VideoProject.objects.create(
            owner=self.user,
            title="Ready Project",
            original_file="test_step2_protection/sample.mp4",
            current_file="test_step2_protection/export2.mp4",
            duration_seconds=1.0,
            status="ready",
        )
        EditOperation.objects.create(
            project=proj,
            operation_type="timeline_export",
            description="Exported JSON Timeline"
        )
        self.assertFalse(proj.has_unexported_edits)
        url = reverse("publish_to_lecture", args=[proj.id]) + f"?recording_id={recording.id}"
        res = self.client.post(url)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res["Location"], reverse("manage_recordings"))
        recording.refresh_from_db()
        self.assertTrue(recording.is_published)
        self.assertEqual(recording.recording_status, "completed")



class TimelineCompilerDetachedAudioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.test_dir = os.path.join(settings.MEDIA_ROOT, "test_detached_audio_media")
        os.makedirs(cls.test_dir, exist_ok=True)
        cls.sample_video_path = os.path.join(cls.test_dir, "sample.mp4")

        # Generate 1-second test video with sine audio
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
            "-c:v", "libx264", "-c:a", "aac",
            cls.sample_video_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        user_model = get_user_model()
        cls.user = user_model.objects.create_user(username="audiouser", password="secretpassword123")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_compile_timeline_with_detached_audio_track(self):
        """Verify non-destructive rendering with detached audio track slices and delays."""
        proj = VideoProject.objects.create(
            owner=self.user,
            title="Audio Test",
            original_file=os.path.relpath(self.sample_video_path, settings.MEDIA_ROOT),
            duration_seconds=1.0,
            has_audio=True,
            status="ready"
        )
        timeline_json = {
            "clips": [
                {"start": 0.0, "end": 0.5, "trimStart": 0.0, "trimEnd": 0.5, "duration": 0.5},
                {"start": 0.5, "end": 1.0, "trimStart": 0.5, "trimEnd": 1.0, "duration": 0.5}
            ],
            "background_audios": [
                {
                    "name": "Audio Track (A1) Part 1",
                    "start": 0.0,
                    "end": 0.4,
                    "trimStart": 0.0,
                    "trimEnd": 0.4,
                    "is_detached": True,
                    "bg_volume": 1.0
                },
                {
                    "name": "Audio Track (A1) Part 2",
                    "start": 0.6,
                    "end": 1.0,
                    "trimStart": 0.6,
                    "trimEnd": 1.0,
                    "is_detached": True,
                    "bg_volume": 1.0
                }
            ],
            "exportResolution": "480p",
            "exportQuality": "low"
        }
        output_path = os.path.join(self.test_dir, "output.mp4")
        compile_timeline_to_ffmpeg(proj, timeline_json, output_path)
        self.assertTrue(os.path.exists(output_path))
        self.assertGreater(os.path.getsize(output_path), 1000)
