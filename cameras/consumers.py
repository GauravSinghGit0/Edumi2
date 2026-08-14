import json
import os
import sys
import subprocess
import asyncio
import threading
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from .models import Camera
from channels.db import database_sync_to_async
from .ffmpeg_helpers import get_ffmpeg_binary

import traceback

logger = logging.getLogger('cameras')

# Dictionary to store the first chunk (header) for each active camera audio stream
# Keys: "mic_{camera_id}", "relay_{camera_id}", or "ip_cam_{camera_id}"
audio_headers = {}
# Active RTSP audio relay processes for teacher monitor {camera_id: subprocess}
rtsp_relays = {}
# Number of listeners per camera relay (teacher monitor) {camera_id: count}
relay_listeners = {}
# Active RTSP audio relay processes for student ip_cam feed {camera_id: subprocess}
ip_cam_relays = {}
# Number of student listeners per ip_cam relay {camera_id: count}
ip_cam_listeners = {}

class AudioConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.camera_id = self.scope['url_route']['kwargs']['camera_id']
        self.user = self.scope['user']
        
        # Get source from query string
        query_params = self.scope.get('query_string', b'').decode()
        self.source = 'pc'
        if 'source=mobile' in query_params:
            self.source = 'mobile'
        elif 'source=pc_monitor' in query_params:
            self.source = 'pc_monitor'
        elif 'source=ip_cam' in query_params:
            self.source = 'ip_cam'
        
        # Initialize mute flag for this connection
        self.is_muted = False
        
        # Group Names:
        # - camera_audio_{id}: For teacher's mic audio OR ip_cam audio (sent to students)
        # - camera_monitor_{id}: For IP camera's internal mic audio (sent to teacher monitor)
        if self.source == 'pc_monitor':
            self.room_group_name = f'camera_monitor_{self.camera_id}'
            self.header_key = f'relay_{self.camera_id}'
        elif self.source == 'ip_cam':
            # Students listening to the camera's built-in mic via RTSP relay
            self.room_group_name = f'camera_audio_{self.camera_id}'
            self.header_key = f'ip_cam_{self.camera_id}'
        else:
            self.room_group_name = f'camera_audio_{self.camera_id}'
            self.header_key = f'mic_{self.camera_id}'
            
        self.is_teacher = await self.check_is_teacher()
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()

        # Handle IP Camera Audio Relay for teacher monitoring
        if self.source == 'pc_monitor':
            if self.camera_id not in relay_listeners:
                relay_listeners[self.camera_id] = 0
            relay_listeners[self.camera_id] += 1

            if relay_listeners[self.camera_id] == 1:
                asyncio.create_task(self.start_rtsp_audio_relay())

        # Handle IP Camera Audio Relay for students (camera's built-in mic)
        elif self.source == 'ip_cam':
            if self.camera_id not in ip_cam_listeners:
                ip_cam_listeners[self.camera_id] = 0
            ip_cam_listeners[self.camera_id] += 1

            if ip_cam_listeners[self.camera_id] == 1:
                asyncio.create_task(self.start_ip_cam_audio_relay())
        
        # Send appropriate header immediately
        if self.header_key in audio_headers:
            await self.send(bytes_data=audio_headers[self.header_key])
        
        if self.is_teacher and self.source != 'pc_monitor':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'mic_status',
                    'source': self.source,
                    'status': 'connected',
                    'user_id': self.user.id
                }
            )
            
            suffix = '_mobile' if self.source == 'mobile' else ''
            self.audio_file_path = os.path.join(settings.MEDIA_ROOT, 'temp', f'audio_{self.camera_id}_{self.user.id}{suffix}.webm')
            os.makedirs(os.path.dirname(self.audio_file_path), exist_ok=True)
            self.audio_file = open(self.audio_file_path, 'wb')
        else:
            self.audio_file = None

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        if self.audio_file:
            self.audio_file.close()
            # If teacher stops mic, clear mic header
            if self.source != 'pc_monitor' and self.header_key in audio_headers:
                del audio_headers[self.header_key]
        
        # Update relay listener count and stop relay if last one
        if self.source == 'pc_monitor' and self.camera_id in relay_listeners:
            relay_listeners[self.camera_id] -= 1
            if relay_listeners[self.camera_id] <= 0:
                self.stop_rtsp_audio_relay()

        # Update ip_cam listener count and stop relay if last student leaves
        elif self.source == 'ip_cam' and self.camera_id in ip_cam_listeners:
            ip_cam_listeners[self.camera_id] -= 1
            if ip_cam_listeners[self.camera_id] <= 0:
                self.stop_ip_cam_audio_relay()

    async def receive(self, text_data=None, bytes_data=None):
        # Handle binary audio chunks (microphone input)
        if bytes_data:
            # Only send audio if not muted and teacher is allowed (or any participant not in monitor mode)
            if not getattr(self, 'is_muted', False) and self.source != 'pc_monitor':
                # Store the first chunk as the header for new students
                if self.header_key not in audio_headers:
                    audio_headers[self.header_key] = bytes_data
                
                if self.audio_file:
                    self.audio_file.write(bytes_data)
                
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'audio_chunk',
                        'data': bytes_data,
                        'sender_channel_name': self.channel_name
                    }
                )
        # Handle textual commands (e.g., mute/unmute) from any user
        if text_data:
            try:
                payload = json.loads(text_data)
                action = payload.get('action')
                if action == 'mute':
                    self.is_muted = True
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'mic_status',
                            'source': self.source,
                            'status': 'muted',
                            'user_id': self.user.id
                        }
                    )
                elif action == 'unmute':
                    self.is_muted = False
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'mic_status',
                            'source': self.source,
                            'status': 'unmuted',
                            'user_id': self.user.id
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to process control message: {e}")

    async def audio_chunk(self, event):
        # Don't send back to the sender
        if self.channel_name != event.get('sender_channel_name'):
            try:
                await self.send(bytes_data=event['data'])
            except Exception as e:
                logger.warning(f"Failed to send audio chunk (likely closed connection): {e}")

    async def mic_status(self, event):
        """Handle mic status updates (connected/disconnected)"""
        # Broadcast status to BOTH audio and monitor groups
        await self.send(text_data=json.dumps({
            'type': 'mic_status',
            'source': event['source'],
            'status': event['status'],
            'user_id': event['user_id']
        }))

    async def check_is_teacher(self):
        try:
            @database_sync_to_async
            def get_camera_teacher():
                try:
                    camera = Camera.objects.get(id=self.camera_id)
                    return camera.live_teacher == self.user or self.user.is_superuser
                except Exception as e:
                    logger.warning(f"Error checking camera teacher: {e}")
                    return False
            return await get_camera_teacher()
        except Exception as e:
            logger.warning(f"Error checking is_teacher: {e}")
            return False

    async def start_rtsp_audio_relay(self):
        """Extracts audio from RTSP and broadcasts to group"""
        if self.camera_id in rtsp_relays:
            return

        # Diagnostic: Log the event loop type
        loop = asyncio.get_running_loop()
        logger.info(f"RTSP Audio Relay starting on loop: {type(loop).__name__}")
        if sys.platform == 'win32' and 'Proactor' not in type(loop).__name__:
            logger.error("WARNING: Not using ProactorEventLoop on Windows! Subprocesses will fail.")

        try:
            camera = await database_sync_to_async(Camera.objects.get)(id=self.camera_id)
            rtsp_url = camera.get_full_rtsp_url()
            
            # THE "ULTIMATE" AUDIO FIX - Attempt 4: High-Sensitivity discovery
            # 1. Increase probe to 40MB - some cameras have huge GOP sizes that hide audio
            # 2. Use -map 0:a? to capture ALL possible audio tracks
            # 3. Apply a massive 20x gain and high-intensity normalization
            cmd = [
                get_ffmpeg_binary(), '-y', '-hide_banner', '-loglevel', 'info',
                '-nostdin',
                '-rtsp_transport', 'tcp', 
                '-probesize', '40M', '-analyzeduration', '40M',
                '-i', rtsp_url,
                '-vn', 
                '-map', '0:a?', 
                '-acodec', 'libopus', '-b:a', '128k', '-ar', '48000', '-ac', '2',
                '-af', 'volume=10.0,aresample=async=1:min_hard_comp=0.1:first_pts=0',
                '-fflags', '+genpts+discardcorrupt+igndts+nobuffer+flush_packets',
                '-f', 'webm',
                'pipe:1'
            ]
            
            logger.info(f"Starting FFmpeg Audio Relay for camera {self.camera_id}")
            
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                is_async_process = True
            except (NotImplementedError, Exception) as e:
                # Catching Exception too because some loop implementations might raise different errors
                # or Python 3.14+ might have changed the error type
                if isinstance(e, NotImplementedError) or "NotImplementedError" in str(type(e)):
                    logger.warning(f"asyncio subprocess not supported on loop {type(loop).__name__}. Falling back to synchronous Popen.")
                else:
                    logger.error(f"Unexpected error starting async subprocess: {e}")
                
                # Fallback: Start process using standard subprocess and a thread to feed the queue
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0 # Unbuffered
                )
                is_async_process = False

            rtsp_relays[self.camera_id] = process
            header_key = f'relay_{self.camera_id}'
            monitor_group = f'camera_monitor_{self.camera_id}'
            
            # Read from pipe and broadcast
            first_chunk = True
            
            while self.camera_id in rtsp_relays:
                try:
                    # Read larger chunks for header and stability
                    chunk_size = 65536 if first_chunk else 4096
                    
                    if is_async_process:
                        chunk = await asyncio.wait_for(process.stdout.read(chunk_size), timeout=15.0)
                    else:
                        # For synchronous process, we use run_in_executor to avoid blocking the event loop
                        chunk = await asyncio.get_event_loop().run_in_executor(
                            None, process.stdout.read, chunk_size
                        )
                    
                    if not chunk:
                        if is_async_process:
                            err_data = await process.stderr.read()
                        else:
                            err_data = process.stderr.read()
                            
                        if err_data:
                            logger.error(f"FFmpeg Relay Error (Cam {self.camera_id}): {err_data.decode()}")
                        break
                    
                    if first_chunk:
                        logger.info(f"Captured Audio Header for Cam {self.camera_id} ({len(chunk)} bytes)")
                        audio_headers[header_key] = chunk
                        first_chunk = False

                    await self.channel_layer.group_send(
                        monitor_group,
                        {
                            'type': 'audio_chunk',
                            'data': chunk,
                            'sender_channel_name': 'rtsp_relay'
                        }
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"RTSP Audio Relay Timeout (Cam {self.camera_id})")
                    break
                except Exception as e:
                    logger.error(f"Error reading from relay pipe: {e}")
                    break
        except Exception as e:
            logger.error(f"RTSP Audio Relay Critical Error (Cam {self.camera_id}): {str(e)}")
            logger.error(traceback.format_exc())
        finally:
            self.stop_rtsp_audio_relay()

    def stop_rtsp_audio_relay(self):
        if self.camera_id in rtsp_relays:
            process = rtsp_relays.pop(self.camera_id)
            try:
                process.terminate()
            except Exception as e:
                logger.warning(f"Error terminating RTSP relay process: {e}")
            
            header_key = f'relay_{self.camera_id}'
            if self.camera_id not in relay_listeners or relay_listeners[self.camera_id] <= 0:
                if header_key in audio_headers:
                    del audio_headers[header_key]

    async def start_ip_cam_audio_relay(self):
        """Extracts audio from RTSP and broadcasts to the student group (camera_audio_{id})."""
        if self.camera_id in ip_cam_relays:
            return

        loop = asyncio.get_running_loop()
        logger.info(f"IP-Cam Audio Relay (students) starting on loop: {type(loop).__name__}")

        try:
            camera = await database_sync_to_async(Camera.objects.get)(id=self.camera_id)
            rtsp_url = camera.get_full_rtsp_url()

            cmd = [
                get_ffmpeg_binary(), '-y', '-hide_banner', '-loglevel', 'warning',
                '-nostdin',
                '-rtsp_transport', 'tcp',
                '-probesize', '40M', '-analyzeduration', '40M',
                '-i', rtsp_url,
                '-vn',
                '-map', '0:a?',
                '-acodec', 'libopus', '-b:a', '128k', '-ar', '48000', '-ac', '2',
                '-af', 'volume=10.0,aresample=async=1:min_hard_comp=0.1:first_pts=0',
                '-fflags', '+genpts+discardcorrupt+igndts+nobuffer+flush_packets',
                '-f', 'webm',
                'pipe:1'
            ]

            logger.info(f"Starting FFmpeg IP-Cam Audio Relay for camera {self.camera_id}")

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                is_async_process = True
            except (NotImplementedError, Exception) as e:
                logger.warning(f"asyncio subprocess not supported ({e}). Falling back to Popen.")
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0
                )
                is_async_process = False

            ip_cam_relays[self.camera_id] = process
            header_key = f'ip_cam_{self.camera_id}'
            student_group = f'camera_audio_{self.camera_id}'

            first_chunk = True

            while self.camera_id in ip_cam_relays:
                try:
                    chunk_size = 65536 if first_chunk else 4096

                    if is_async_process:
                        chunk = await asyncio.wait_for(process.stdout.read(chunk_size), timeout=15.0)
                    else:
                        chunk = await asyncio.get_event_loop().run_in_executor(
                            None, process.stdout.read, chunk_size
                        )

                    if not chunk:
                        if is_async_process:
                            err_data = await process.stderr.read()
                        else:
                            err_data = process.stderr.read()
                        if err_data:
                            logger.error(f"FFmpeg IP-Cam Relay Error (Cam {self.camera_id}): {err_data.decode()}")
                        break

                    if first_chunk:
                        logger.info(f"IP-Cam Audio Header captured for Cam {self.camera_id} ({len(chunk)} bytes)")
                        audio_headers[header_key] = chunk
                        first_chunk = False

                    await self.channel_layer.group_send(
                        student_group,
                        {
                            'type': 'audio_chunk',
                            'data': chunk,
                            'sender_channel_name': 'ip_cam_relay'
                        }
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"IP-Cam Audio Relay Timeout (Cam {self.camera_id})")
                    break
                except Exception as e:
                    logger.error(f"Error reading from IP-Cam relay pipe: {e}")
                    break
        except Exception as e:
            logger.error(f"IP-Cam Audio Relay Critical Error (Cam {self.camera_id}): {str(e)}")
            logger.error(traceback.format_exc())
        finally:
            self.stop_ip_cam_audio_relay()

    def stop_ip_cam_audio_relay(self):
        if self.camera_id in ip_cam_relays:
            process = ip_cam_relays.pop(self.camera_id)
            try:
                process.terminate()
            except Exception as e:
                logger.warning(f"Error terminating IP-Cam relay process: {e}")

            header_key = f'ip_cam_{self.camera_id}'
            if self.camera_id not in ip_cam_listeners or ip_cam_listeners[self.camera_id] <= 0:
                if header_key in audio_headers:
                    del audio_headers[header_key]
