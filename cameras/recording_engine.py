import os
import subprocess
import threading
import logging
import time
import signal
from django.conf import settings
from django.utils import timezone
from .models import Camera, CameraRecording
from .ffmpeg_helpers import get_ffmpeg_binary

logger = logging.getLogger('cameras')

class RecordingEngine:
    """FFmpeg-based recording engine for high-quality AV synchronization"""
    
    _instances = {}
    _lock = threading.RLock()

    def __init__(self, camera_id, teacher_id, audio_path=None, is_chunked=True):
        self.camera_id = camera_id
        self.teacher_id = teacher_id
        self.process = None
        self.output_path = None
        self.audio_path = audio_path  # External audio file from browser
        self.recording_id = None
        self.start_time = None
        self.finalized = False
        self.is_chunked = is_chunked
        self.chunk_sequence = 0
        self.lock = threading.RLock()  # Use RLock to prevent re-entrant deadlocks during monitor callback

    @classmethod
    def start_recording(cls, camera, teacher, quality='1080p', audio_source='pc', is_chunked=True):
        with cls._lock:
            key = f"{camera.id}_{teacher.id}"
            
            # 1. Check if ANYONE is already recording this camera
            for k, existing in cls._instances.items():
                if k.startswith(f"{camera.id}_"):
                    if existing.process and existing.process.poll() is None:
                        return False, "This camera is already being recorded by another session"
                    else:
                        logger.warning(f"Found stale recording instance for {k}, cleaning up.")
                        del cls._instances[k]
                        break

            # 2. Check DB for orphaned 'recording' status on this camera
            from .models import CameraRecording
            orphaned = CameraRecording.objects.filter(camera=camera, recording_status='recording')
            if orphaned.exists():
                logger.warning(f"Found orphaned DB records for camera {camera.id}, marking as failed before starting new.")
                orphaned.update(recording_status='failed')

            final_audio_path = None
            
            if audio_source == 'camera':
                # Use built-in camera audio, no external path needed
                logger.info(f"Using IP Camera built-in audio for recording")
            elif audio_source == 'remote':
                # Force mobile mic
                mobile_audio_path = os.path.join(settings.MEDIA_ROOT, 'temp', f'audio_{camera.id}_{teacher.id}_mobile.webm')
                if os.path.exists(mobile_audio_path):
                    final_audio_path = mobile_audio_path
                    logger.info(f"Using REMOTE mobile mic for recording: {mobile_audio_path}")
            else:
                # Default to PC mic or auto-detect
                mobile_audio_path = os.path.join(settings.MEDIA_ROOT, 'temp', f'audio_{camera.id}_{teacher.id}_mobile.webm')
                pc_audio_path = os.path.join(settings.MEDIA_ROOT, 'temp', f'audio_{camera.id}_{teacher.id}.webm')
                
                # Auto-detect logic
                if os.path.exists(mobile_audio_path) and (time.time() - os.path.getmtime(mobile_audio_path)) < 60:
                    final_audio_path = mobile_audio_path
                elif os.path.exists(pc_audio_path) and (time.time() - os.path.getmtime(pc_audio_path)) < 60:
                    final_audio_path = pc_audio_path

            instance = cls(camera.id, teacher.id, audio_path=final_audio_path, is_chunked=is_chunked)
            success, msg = instance._start(camera, teacher, quality)
            if success:
                cls._instances[key] = instance
            return success, msg

    def _start(self, camera, teacher, quality):
        # Determine separate folder: 'streams' if camera is live, else 'recordings'
        subfolder = 'streams' if camera.is_live else 'recordings'
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        
        if self.is_chunked:
            # For chunked, we use a directory for the chunks
            filename_pattern = "chunk_%03d.ts"
            relative_dir = os.path.join('recordings', teacher.username, subfolder, f"rec_{camera.id}_{timestamp}")
            self.output_path = os.path.join(settings.MEDIA_ROOT, relative_dir, filename_pattern)
            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        else:
            filename = f"rec_{camera.id}_{timestamp}.mkv"  # Record to MKV for crash resilience
            relative_path = os.path.join('recordings', teacher.username, subfolder, filename)
            self.output_path = os.path.join(settings.MEDIA_ROOT, relative_path)
            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        
        # Map quality to resolution
        quality_map = {
            '360p': '640x360',
            '480p': '854x480',
            '720p': '1280x720',
            '1080p': '1920x1080',
            '4K': '3840x2160'
        }
        res = quality_map.get(quality, '1280x720')

        # Determine encoder: Use hardware-accelerated if available, else libx264
        encoder = 'libx264'
        try:
            test_cmd = [get_ffmpeg_binary(), '-hide_banner', '-encoders']
            encoders_output = subprocess.check_output(test_cmd, stderr=subprocess.STDOUT).decode()
            if 'h264_amf' in encoders_output:
                encoder = 'h264_amf'
            elif 'h264_nvenc' in encoders_output:
                encoder = 'h264_nvenc'
            elif 'h264_qsv' in encoders_output:
                encoder = 'h264_qsv'
        except Exception as e:
            logger.warning(f"Failed to detect encoders, using libx264: {e}")

        logger.info(f"Using encoder: {encoder} for recording")

        # Build robust FFmpeg command
        cmd = [
            get_ffmpeg_binary(), '-y',
            '-hide_banner',
            '-loglevel', 'info',
            '-probesize', '100M',
            '-analyzeduration', '100M',
            '-thread_queue_size', '4096'
        ]

        stream_url = camera.get_stream_url()
        if stream_url and stream_url.startswith('rtsp'):
            cmd.extend(['-rtsp_transport', 'tcp', '-fflags', '+nobuffer', '-flags', '+low_delay'])
        if stream_url:
            cmd.extend(['-i', stream_url])

        # Add audio input if available
        if self.audio_path and os.path.exists(self.audio_path):
            cmd.extend([
                '-itsoffset', '1.0',
                '-probesize', '50M', '-analyzeduration', '50M',
                '-i', self.audio_path
            ])

        cmd.extend(['-s', res, '-c:v', encoder])

        # Encoder-specific options
        if encoder in ['h264_amf', 'h264_nvenc', 'h264_qsv']:
            cmd.extend(['-quality', 'balanced', '-rc', 'cbr', '-b:v', '4M' if quality == '4K' else '2.5M'])
        else:
            cmd.extend(['-preset', 'ultrafast', '-crf', '23', '-profile:v', 'main'])

        cmd.extend(['-pix_fmt', 'yuv420p'])

        audio_input_index = '1' if (self.audio_path and os.path.exists(self.audio_path)) else None
        cmd.extend(['-map', '0:v:0'])
        if audio_input_index:
            cmd.extend([
                '-map', f'{audio_input_index}:a:0',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ar', '44100',
                '-af', 'aresample=async=1000:min_hard_comp=0.1:first_pts=0'
            ])
        else:
            cmd.extend([
                '-map', '0:a:0?',
                '-c:a', 'aac',
                '-b:a', '128k'
            ])

        if self.is_chunked:
            cmd.extend([
                '-f', 'segment',
                '-segment_time', '10',
                '-segment_format', 'mpegts',
                '-segment_list_type', 'm3u8',
                '-segment_list', self.output_path.replace('chunk_%03d.ts', 'index.m3u8'),
                '-reset_timestamps', '1',
                self.output_path
            ])
        else:
            cmd.extend([
                '-vsync', 'cfr',
                '-f', 'matroska',
                self.output_path
            ])

        try:
            # Create the Recording record
            rec = CameraRecording.objects.create(
                camera=camera,
                teacher=teacher,
                title=f"Recording - {camera.name} - {timestamp}",
                recording_status='recording',
                is_chunked=self.is_chunked,
                video_file=os.path.relpath(self.output_path if not self.is_chunked else os.path.dirname(self.output_path), settings.MEDIA_ROOT).replace('\\', '/')
            )
            self.recording_id = rec.id
            self.start_time = timezone.now()

            logger.info(f"Starting FFmpeg with command: {' '.join(cmd)}")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            
            time.sleep(2)
            if self.process.poll() is not None:
                stderr = self.process.stderr.read().decode()
                logger.error(f"FFmpeg failed to start: {stderr}")
                rec.recording_status = 'failed'
                rec.save()
                return False, "FFmpeg failed to start recording"

            logger.info(f"Started FFmpeg recording for camera {camera.id} at {self.output_path}")
            
            # Start monitoring threads
            threading.Thread(target=self._monitor_process, daemon=True).start()
            if self.is_chunked:
                threading.Thread(target=self._chunk_watcher, daemon=True).start()
            
            return True, "Recording started"
        except Exception as e:
            logger.error(f"Failed to start recording: {e}", exc_info=True)
            return False, str(e)

    def _chunk_watcher(self):
        """Monitor directory for new segments and save to DB"""
        chunk_dir = os.path.dirname(self.output_path)
        last_chunk = -1
        
        while not self.finalized:
            try:
                # Find all .ts files in the directory
                chunks = sorted([f for f in os.listdir(chunk_dir) if f.endswith('.ts')])
                
                # We save all chunks EXCEPT the last one (which might still be being written)
                # Unless the process has stopped
                if len(chunks) > 1:
                    to_process = chunks[:-1]
                    for chunk_file in to_process:
                        chunk_idx = int(chunk_file.replace('chunk_', '').replace('.ts', ''))
                        if chunk_idx > last_chunk:
                            self._save_chunk_to_db(os.path.join(chunk_dir, chunk_file), chunk_idx)
                            last_chunk = chunk_idx
                            # Delete the file after saving to DB to save space
                            try: os.remove(os.path.join(chunk_dir, chunk_file))
                            except Exception as e:
                                logger.warning(f"Failed to remove chunk file: {e}")
                
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error in chunk watcher: {e}")
                time.sleep(5)

    def _save_chunk_to_db(self, file_path, sequence):
        """Read chunk file and save as RecordingChunk"""
        try:
            from .models import CameraRecording, RecordingChunk
            with open(file_path, 'rb') as f:
                data = f.read()
            
            if len(data) > 0:
                rec = CameraRecording.objects.get(id=self.recording_id)
                RecordingChunk.objects.create(
                    recording=rec,
                    sequence=sequence,
                    data=data,
                    duration=10.0  # Standard segment time
                )
                logger.info(f"Saved chunk {sequence} for recording {self.recording_id} to DB")
        except Exception as e:
            logger.error(f"Failed to save chunk {sequence} to DB: {e}")

    def _monitor_process(self):
        """Monitor the FFmpeg process, enforce a 12-hour limit, and auto-save if it stops unexpectedly"""
        max_duration = 12 * 3600  # 12 hours in seconds
        poll_interval = 2.0
        
        while True:
            # Check if deliberately finalized
            with self.lock:
                if self.finalized:
                    break
            
            # Check if process ended naturally
            if self.process.poll() is not None:
                break
                
            # Check elapsed duration since start
            elapsed = (timezone.now() - self.start_time).total_seconds()
            if elapsed >= max_duration:
                logger.warning(f"Recording for camera {self.camera_id} reached 12-hour limit. Stopping.")
                self._stop(auto_save=True)
                break
                
            time.sleep(poll_interval)

        # Wait for the process to exit completely (if not already done)
        try:
            self.process.wait(timeout=5)
        except Exception:
            pass

        # We use a slight delay to ensure file handles are released before finalization
        time.sleep(1)
        
        should_cleanup = False
        with self.lock:
            if not self.finalized:
                logger.warning(f"FFmpeg process for camera {self.camera_id} stopped unexpectedly. Auto-saving...")
                self._stop(auto_save=True)
                should_cleanup = True
            else:
                # Deliberate stop handled it, but we still need to ensure cleanup
                should_cleanup = True
        
        if should_cleanup:
            # Remove from active instances OUTSIDE the instance lock to prevent AB-BA deadlock
            key = f"{self.camera_id}_{self.teacher_id}"
            with RecordingEngine._lock:
                if RecordingEngine._instances.get(key) == self:
                    del RecordingEngine._instances[key]

    @classmethod
    def stop_recording(cls, camera_id, teacher_id):
        with cls._lock:
            from .models import CameraRecording

            # 1. First, look for any recording instance in memory for this camera,
            # regardless of teacher (since only one can be recording per camera)
            instance = None
            key = None
            for k, v in cls._instances.items():
                if k.startswith(f"{camera_id}_"):
                    instance = v
                    key = k
                    break
            
            # 2. Look for active DB record for this camera
            active_rec = CameraRecording.objects.filter(
                camera_id=camera_id, 
                recording_status='recording'
            ).last()
        
        # If we have an instance in memory, stop it first
        if instance:
            try:
                logger.info(f"Stopping recording instance {key}")
                instance._stop(auto_save=False)
                
                # Cleanup the instance from memory
                with cls._lock:
                    if key in cls._instances:
                        del cls._instances[key]
                
                # Return the recording ID from the instance
                return True, instance.recording_id
            except Exception as e:
                logger.error(f"Error stopping instance: {e}")
                # Don't fail completely, try DB fallback below
        
        # If we found a DB record but no memory instance, finalize it
        if active_rec:
            logger.warning(f"Found DB record {active_rec.id} for camera {camera_id} without memory instance, finalizing")
            active_rec.recording_status = 'processing'
            active_rec.save()
            try:
                from .tasks import process_recording_task
                process_recording_task.delay(active_rec.id)
            except Exception as e:
                logger.error(f"Failed to trigger processing task: {e}")
                active_rec.recording_status = 'completed'
                active_rec.save()
            return True, active_rec.id
        
        # If all else fails, at least return the last recording for that camera and teacher
        last_rec = CameraRecording.objects.filter(
            camera_id=camera_id, 
            teacher_id=teacher_id
        ).order_by('-created_at').first()
        if last_rec:
            logger.warning(f"No active recording, but returning last recording {last_rec.id} for user")
            return True, last_rec.id
        
        logger.error(f"No active recording found for camera {camera_id}")
        return False, "No active recording found"

    @classmethod
    def is_recording(cls, camera_id, teacher_id):
        with cls._lock:
            # 1. Check memory for ANY instance on this camera
            for k, instance in cls._instances.items():
                if k.startswith(f"{camera_id}_"):
                    if instance.process and instance.process.poll() is None:
                        return True, instance.start_time
                    else:
                        # Clean up stale instance
                        del cls._instances[k]
                        break
            
            # 2. Fallback to DB check for this camera
            from .models import CameraRecording
            active_rec = CameraRecording.objects.filter(
                camera_id=camera_id, 
                recording_status='recording'
            ).last()
            if active_rec:
                return True, active_rec.created_at
                
            return False, None

    @classmethod
    def get_active_session(cls, camera_id):
        """Return the active recording instance for a camera, or None."""
        with cls._lock:
            for k, instance in list(cls._instances.items()):
                if k.startswith(f"{camera_id}_"):
                    if instance.process and instance.process.poll() is None:
                        return instance
        return None

    def _stop(self, auto_save=False):
        with self.lock:
            if self.finalized:
                return True
            
            if self.process:
                try:
                    logger.info(f"Finalizing recording for camera {self.camera_id} (Auto-save: {auto_save})")
                    
                    # If manual stop, terminate the process gracefully
                    if not auto_save and self.process.poll() is None:
                        logger.info(f"Sending termination signal to FFmpeg (PID: {self.process.pid})")
                        try:
                            if os.name == 'nt':
                                import signal
                                os.kill(self.process.pid, signal.CTRL_BREAK_EVENT)
                            else:
                                self.process.terminate()
                            
                            # Wait for process to exit and flush headers (blocking for up to 5s)
                            try:
                                self.process.wait(timeout=5)
                                logger.info("FFmpeg process terminated gracefully and flushed headers.")
                            except subprocess.TimeoutExpired:
                                logger.warning("FFmpeg did not exit in time, forcing kill...")
                                self.process.kill()
                        except Exception as e:
                            logger.error(f"Error terminating FFmpeg: {e}")
                            try: self.process.kill()
                            except: pass
                    
                    # Update database logic stays the same but without waiting for process
                    try:
                        rec = CameraRecording.objects.get(id=self.recording_id)
                    except CameraRecording.DoesNotExist:
                        logger.error(f"Recording record {self.recording_id} not found during stop")
                        self.finalized = True
                        return False
                    
                    if auto_save:
                        rec.title = f"[AUTO-SAVED] {rec.title}"
                    
                    # For chunked recordings, process the remaining chunks
                    if self.is_chunked:
                        self.finalized = True  # Signal watcher to stop
                        chunk_dir = os.path.dirname(self.output_path)
                        if os.path.exists(chunk_dir):
                            remaining_chunks = sorted([f for f in os.listdir(chunk_dir) if f.endswith('.ts')])
                            for chunk_file in remaining_chunks:
                                chunk_idx = int(chunk_file.replace('chunk_', '').replace('.ts', ''))
                                self._save_chunk_to_db(os.path.join(chunk_dir, chunk_file), chunk_idx)
                                try: os.remove(os.path.join(chunk_dir, chunk_file))
                                except: pass
                            
                            # Clean up the directory if empty
                            try: os.rmdir(chunk_dir)
                            except: pass
                        
                        rec.recording_status = 'completed'
                        rec.duration = timezone.now() - self.start_time
                        rec.save()
                        
                        # Generate thumbnail from chunks
                        try:
                            rec.generate_chunked_thumbnail()
                        except Exception as e:
                            logger.error(f"Failed to generate chunked thumbnail: {e}")
                            
                        return True

                    # Check if file exists and has size (for non-chunked)
                    if os.path.exists(self.output_path):
                        file_size = os.path.getsize(self.output_path)
                        if file_size > 0:
                            # Mark as processing and return quickly
                            # Remuxing and thumbnails will happen in the background task
                            rec.recording_status = 'processing'
                            rec.duration = timezone.now() - self.start_time
                            
                            # Set the file field (currently .mkv)
                            relative_path = os.path.relpath(self.output_path, settings.MEDIA_ROOT)
                            rec.video_file.name = relative_path.replace('\\', '/')
                            rec.file_size = file_size
                            rec.save()
                            
                            # Trigger background processing (includes MKV -> MP4 remuxing)
                            try:
                                from .tasks import process_recording_task
                                process_recording_task.delay(rec.id)
                                logger.info(f"Recording {self.recording_id} stop requested, sent to background processing")
                            except Exception as e:
                                logger.error(f"Failed to trigger Celery task: {e}")
                                # Fallback: mark as completed if Celery fails
                                rec.recording_status = 'completed'
                                rec.save()
                            
                            self.finalized = True
                            return True
                        else:
                            logger.error(f"Recording file for camera {self.camera_id} is empty")
                            rec.recording_status = 'failed'
                            rec.save()
                            self.finalized = True
                            return False
                    else:
                        logger.error(f"Recording file for camera {self.camera_id} does not exist at {self.output_path}")
                        rec.recording_status = 'failed'
                        rec.save()
                        self.finalized = True
                        return False
                        
                except Exception as e:
                    logger.error(f"Error stopping recording: {e}")
                    self.finalized = True
                    return False
            return False

recording_engine = RecordingEngine

def cleanup_orphaned_recordings():
    """Find recordings stuck in 'recording' state and mark as failed or recover if file exists"""
    try:
        from .models import CameraRecording
        from django.db import connection
        
        # Comprehensive check for table existence
        all_tables = connection.introspection.table_names()
        if "cameras_camerarecording" not in all_tables:
            return

        orphaned = CameraRecording.objects.filter(recording_status='recording')
    except Exception as e:
        # Silently fail if DB or table is not ready
        return

    for rec in orphaned:
        # If it's more than 5 minutes old and not in our active instances, it's orphaned
        rec_time = rec.created_at
        if (timezone.now() - rec_time).total_seconds() > 300:
            logger.warning(f"Found orphaned recording {rec.id}. Attempting recovery...")
            # Check if file exists in media
            if rec.video_file and os.path.exists(rec.video_file.path):
                rec.recording_status = 'completed'
                rec.title = f"[RECOVERED] {rec.title}"
            else:
                # Try to find the file manually if field is empty
                # Look for .mkv or .mp4 files that might match
                rec.recording_status = 'failed'
            rec.save()
