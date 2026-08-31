import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Meeting, MeetingParticipant, MeetingAttendanceLog, MeetingChat
from cameras.models import Camera

User = get_user_model()

logger = logging.getLogger(__name__)

# Global tracking for CAM_* rooms (non-persistent)
cam_room_participants = {}

class MeetingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            self.meeting_code = self.scope['url_route']['kwargs']['meeting_code'].upper()
            self.room_group_name = f'meeting_{self.meeting_code}'
            self.user = self.scope.get('user')
            
            if not self.user or not self.user.is_authenticated:
                await self.close()
                return

            # Accept connection first to complete handshake and prevent ERR_CONNECTION_RESET
            await self.accept()

            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            # Record join and get user meta
            user_data = await self.get_user_meta()

            # Track for CAM_* rooms
            if self.meeting_code.startswith('CAM_'):
                if self.meeting_code not in cam_room_participants:
                    cam_room_participants[self.meeting_code] = {}
                cam_room_participants[self.meeting_code][self.user.id] = self.user.username
            
            # Get other active participants safely
            active_participants = await self.get_active_participants()

            # Send current participant list to the joiner
            await self.send(text_data=json.dumps({
                'type': 'participant_list',
                'participants': active_participants
            }))

            # Notify others that user joined
            if user_data:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_joined',
                        'user_id': user_data['id'],
                        'username': user_data['username'],
                        'display_name': user_data.get('display_name', user_data['username']),
                        'pfp_url': user_data.get('pfp_url', ''),
                        'is_host': user_data.get('is_host', False),
                        'is_admin': user_data.get('is_admin', False),
                    }
                )
        except Exception as e:
            logger.error(f"WS Connect Error in MeetingConsumer: {str(e)}", exc_info=True)
            try:
                await self.close()
            except Exception:
                pass

    @database_sync_to_async
    def get_user_meta(self):
        from common.utils import get_user_display_name, get_user_avatar_url
        try:
            meeting = Meeting.objects.get(meeting_code=self.meeting_code)
            # Record join while we are here
            participant, _ = MeetingParticipant.objects.get_or_create(
                meeting=meeting,
                user=self.user
            )
            
            # Only log 'join' if the user was not already active or last log was 'leave'
            last_log = MeetingAttendanceLog.objects.filter(participant=participant).order_by('timestamp').last()
            if not participant.is_active or (last_log and last_log.event_type == 'leave'):
                MeetingAttendanceLog.objects.create(
                    participant=participant,
                    event_type='join'
                )
                
            participant.joined_at = timezone.now()
            participant.is_active = True
            participant.save()
            
            return {
                'id': self.user.id,
                'username': self.user.username,
                'display_name': get_user_display_name(self.user),
                'pfp_url': get_user_avatar_url(self.user),
                'is_host': meeting.teacher == self.user or bool(self.user.is_superuser),
                'is_admin': bool(self.user.is_superuser)
            }
        except Meeting.DoesNotExist:
             # Handle CAM_* rooms for live lectures
             if self.meeting_code.startswith('CAM_'):
                 parts = self.meeting_code.split('_')
                 camera_id = parts[1] if len(parts) > 1 else None
                 is_host = False
                 if camera_id:
                     try:
                         camera = Camera.objects.get(id=camera_id)
                         is_host = (camera.live_teacher == self.user) or bool(self.user.is_superuser)
                     except Exception as e:
                         logger.warning(f"Error checking camera host status: {e}")
                     
                 return {
                     'id': self.user.id,
                     'username': self.user.username,
                     'display_name': get_user_display_name(self.user),
                     'pfp_url': get_user_avatar_url(self.user),
                     'is_host': is_host,
                     'is_admin': bool(self.user.is_superuser)
                 }
             raise

    @database_sync_to_async
    def get_active_participants(self):
        from common.utils import get_user_display_name, get_user_avatar_url
        try:
            meeting = Meeting.objects.get(meeting_code=self.meeting_code)
            # Find all users who are marked active in this meeting, excluding self
            active = MeetingParticipant.objects.filter(
                meeting=meeting, 
                is_active=True
            ).exclude(user=self.user).select_related('user', 'user__userprofile')
            
            return [
                {
                    'user_id': p.user.id,
                    'username': p.user.username,
                    'display_name': get_user_display_name(p.user),
                    'pfp_url': get_user_avatar_url(p.user),
                    'is_host': meeting.teacher == p.user or bool(p.user.is_superuser),
                    'is_admin': bool(p.user.is_superuser)
                } for p in active
            ]
        except Meeting.DoesNotExist:
            if self.meeting_code.startswith('CAM_'):
                # Return from in-memory tracking safely
                participants = dict(cam_room_participants.get(self.meeting_code, {}))
                return [
                    {
                        'user_id': uid,
                        'username': uname,
                        'display_name': uname,
                        'pfp_url': f"https://ui-avatars.com/api/?name={uname}&background=1877f2&color=fff",
                        'is_host': False,
                        'is_admin': False
                    }
                    for uid, uname in list(participants.items())
                    if uid != self.user.id
                ]
            return []
        except Exception as e:
            logger.warning(f"Error fetching active participants: {e}")
            return []
    
    async def disconnect(self, close_code):
        # Guard: if connect() failed before attributes were set, skip cleanup
        if not hasattr(self, 'meeting_code') or not hasattr(self, 'user'):
            return

        # Remove from tracking for CAM_* rooms
        if self.meeting_code.startswith('CAM_'):
            if self.meeting_code in cam_room_participants:
                cam_room_participants[self.meeting_code].pop(self.user.id, None)

        # Notify others that user left
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_left',
                'user_id': self.user.id,
                'username': self.user.username
            }
        )
        
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        # Record leave in database
        await self.record_leave()
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            logger.debug(
                "WS RECV: user=%s message_type=%s to=%s",
                self.user.id, message_type, data.get('to_user_id')
            )

            if message_type == 'offer':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'webrtc_offer',
                        'offer': data['offer'],
                        'from_user_id': self.user.id,
                        'from_username': self.user.username,
                        'to_user_id': data.get('to_user_id')
                    }
                )
            
            elif message_type == 'answer':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'webrtc_answer',
                        'answer': data['answer'],
                        'from_user_id': self.user.id,
                        'from_username': self.user.username,
                        'to_user_id': data.get('to_user_id')
                    }
                )
            
            elif message_type == 'ice_candidate':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'ice_candidate',
                        'candidate': data['candidate'],
                        'from_user_id': self.user.id,
                        'to_user_id': data.get('to_user_id')
                    }
                )
            
            elif message_type == 'chat':
                if 'message' in data:
                    chat_meta = await self.save_chat_message(data['message'])
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'chat_message',
                            'message': data['message'],
                            'username': self.user.username,
                            'display_name': chat_meta.get('display_name', self.user.username),
                            'pfp_url': chat_meta.get('pfp_url', ''),
                            'user_id': self.user.id,
                            'timestamp': data.get('timestamp', timezone.now().isoformat())
                        }
                    )
            
            elif message_type == 'screen_share_started':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'screen_share_started',
                        'user_id': self.user.id,
                        'username': self.user.username
                    }
                )
            
            elif message_type == 'screen_share_stopped':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'screen_share_stopped',
                        'user_id': self.user.id,
                        'username': self.user.username
                    }
                )
            
            elif message_type == 'request_participants':
                active_participants = await self.get_active_participants()
                await self.send(text_data=json.dumps({
                    'type': 'participant_list',
                    'participants': active_participants
                }))
            
            elif message_type == 'check_time_limit':
                await self.process_expiration_check()

            elif message_type == 'continue_meeting':
                await self.process_continue_meeting()

            elif message_type == 'start_recording':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'recording_started',
                        'host_name': self.user.username
                    }
                )

            elif message_type == 'stop_recording':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'recording_stopped',
                        'host_name': self.user.username
                    }
                )

            elif message_type == 'quiz_tab_switch_warning':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'quiz_tab_switch_warning',
                        'student_id': self.user.id,
                        'student_name': data.get('student_name', self.user.username),
                        'tab_switch_count': data.get('tab_switch_count', 1),
                        'timestamp': data.get('timestamp', timezone.now().strftime('%H:%M:%S'))
                    }
                )
        except Exception as e:
            logger.error(f"Receive error: {e}")

    async def recording_started(self, event):
        """Handle recording started notification"""
        await self.send(text_data=json.dumps({
            'type': 'recording_started',
            'host_name': event.get('host_name', 'Host'),
            'message': 'Meeting is being recorded by the host.'
        }))

    async def recording_stopped(self, event):
        """Handle recording stopped notification"""
        await self.send(text_data=json.dumps({
            'type': 'recording_stopped',
            'host_name': event.get('host_name', 'Host'),
            'message': 'Meeting recording stopped.'
        }))

    async def time_limit_expired_prompt(self, event):
        """Handle time limit expiration prompt event for host"""
        await self.send(text_data=json.dumps({
            'type': 'time_limit_expired_prompt',
            'message': event.get('message', 'The scheduled meeting time has ended. Do you want to continue the meeting?')
        }))

    async def meeting_continued(self, event):
        """Handle meeting extension/continuation event"""
        await self.send(text_data=json.dumps({
            'type': 'meeting_continued',
            'message': event.get('message', 'Meeting continuation granted by host.')
        }))

    async def meeting_ended(self, event):
        """Handle meeting ended notification"""
        await self.send(text_data=json.dumps({
            'type': 'meeting_ended',
            'reason': event.get('reason', 'host_ended'),
            'message': event.get('message', 'The meeting has ended.')
        }))

    @database_sync_to_async
    def process_expiration_check(self):
        from .services import check_and_process_meeting_expiration
        try:
            meeting = Meeting.objects.get(meeting_code=self.meeting_code)
            check_and_process_meeting_expiration(meeting)
        except Meeting.DoesNotExist:
            pass

    @database_sync_to_async
    def process_continue_meeting(self):
        try:
            meeting = Meeting.objects.get(meeting_code=self.meeting_code)
            if meeting.teacher == self.user or self.user.is_superuser:
                meeting.is_extended = True
                meeting.save(update_fields=['is_extended'])
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f'meeting_{self.meeting_code}',
                        {
                            'type': 'meeting_continued',
                            'message': 'Meeting continuation granted by host.',
                        }
                    )
        except Meeting.DoesNotExist:
            pass
    
    async def user_joined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_joined',
            'user_id': event['user_id'],
            'username': event['username'],
            'display_name': event.get('display_name', event['username']),
            'pfp_url': event.get('pfp_url', ''),
            'is_host': event.get('is_host', False),
            'is_admin': event.get('is_admin', False),
        }))
    
    async def user_left(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_left',
            'user_id': event['user_id'],
            'username': event['username']
        }))
    
    async def webrtc_offer(self, event):
        # Only send to intended recipient
        if event.get('to_user_id') == self.user.id or event.get('to_user_id') is None:
            await self.send(text_data=json.dumps({
                'type': 'offer',
                'offer': event['offer'],
                'from_user_id': event['from_user_id'],
                'from_username': event['from_username']
            }))
    
    async def webrtc_answer(self, event):
        # Only send to intended recipient
        if event.get('to_user_id') == self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'answer',
                'answer': event['answer'],
                'from_user_id': event['from_user_id'],
                'from_username': event['from_username']
            }))
    
    async def ice_candidate(self, event):
        # Only send to intended recipient
        if event.get('to_user_id') == self.user.id or event.get('to_user_id') is None:
            await self.send(text_data=json.dumps({
                'type': 'ice_candidate',
                'candidate': event['candidate'],
                'from_user_id': event['from_user_id']
            }))
    
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat',
            'message': event['message'],
            'username': event['username'],
            'display_name': event.get('display_name', event['username']),
            'pfp_url': event.get('pfp_url', ''),
            'user_id': event['user_id'],
            'timestamp': event.get('timestamp')
        }))
    
    async def screen_share_started(self, event):
        await self.send(text_data=json.dumps({
            'type': 'screen_share_started',
            'user_id': event['user_id'],
            'username': event['username']
        }))
    
    async def screen_share_stopped(self, event):
        await self.send(text_data=json.dumps({
            'type': 'screen_share_stopped',
            'user_id': event['user_id'],
            'username': event['username']
        }))

    async def quiz_started(self, event):
        await self.send(text_data=json.dumps({
            'type': 'quiz_started',
            'quiz': event['quiz'],
            'host_name': event.get('host_name', 'Teacher')
        }))

    async def quiz_submitted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'quiz_submitted',
            'student_id': event['student_id'],
            'student_name': event['student_name'],
            'quiz_id': event['quiz_id'],
            'tab_switch_count': event.get('tab_switch_count', 0),
            'marks_obtained': event.get('marks_obtained', 0),
            'total_marks': event.get('total_marks', 0)
        }))

    async def quiz_tab_switch_warning(self, event):
        await self.send(text_data=json.dumps({
            'type': 'quiz_tab_switch_warning',
            'student_id': event['student_id'],
            'student_name': event['student_name'],
            'tab_switch_count': event.get('tab_switch_count', 1),
            'timestamp': event.get('timestamp', '')
        }))

    async def meeting_sleeping(self, event):
        """Handle meeting sleep notification"""
        await self.send(text_data=json.dumps({
            'type': 'meeting_sleeping',
            'message': event.get('message', 'Meeting has been put to sleep')
        }))
    
    async def meeting_unfrozen(self, event):
        """Handle meeting unfrozen notification"""
        await self.send(text_data=json.dumps({
            'type': 'meeting_unfrozen',
            'message': event.get('message', 'Meeting is now active')
        }))
    
    async def kick_user(self, event):
        """Handle user kick notification"""
        await self.send(text_data=json.dumps({
            'type': 'kick_user',
            'user_id': event['user_id'],
            'message': event['message']
        }))
        if self.user.id == event['user_id']:
            await self.close()

    async def permission_update(self, event):
        """Handle participant permission update"""
        await self.send(text_data=json.dumps({
            'type': 'permission_update',
            'user_id': event['user_id'],
            'permission_type': event['permission_type'],
            'value': event['value'],
            'message': event['message']
        }))

    async def global_control_update(self, event):
        """Handle global control update (mute all, etc.)"""
        await self.send(text_data=json.dumps({
            'type': 'global_control_update',
            'control_type': event['control_type'],
            'value': event['value'],
            'message': event['message']
        }))
    
    @database_sync_to_async
    def get_meeting(self):
        try:
            return Meeting.objects.get(meeting_code=self.meeting_code)
        except Meeting.DoesNotExist:
            return None

    @database_sync_to_async
    def record_join(self):
        try:
            meeting = Meeting.objects.get(meeting_code=self.meeting_code)
            participant, created = MeetingParticipant.objects.get_or_create(
                meeting=meeting,
                user=self.user
            )
            
            # Only log 'join' if the user was not already active or last log was 'leave'
            last_log = MeetingAttendanceLog.objects.filter(participant=participant).order_by('timestamp').last()
            if not participant.is_active or (last_log and last_log.event_type == 'leave'):
                MeetingAttendanceLog.objects.create(
                    participant=participant,
                    event_type='join'
                )

            participant.joined_at = timezone.now()
            participant.is_active = True
            participant.save()
        except Meeting.DoesNotExist:
            pass # No persistence for CAM_* rooms
        except Exception as e:
            logger.error(f"Error recording join: {e}")

    @database_sync_to_async
    def record_leave(self):
        try:
            meeting = Meeting.objects.get(meeting_code=self.meeting_code)
            participant = MeetingParticipant.objects.get(
                meeting=meeting,
                user=self.user
            )
            
            if not participant.is_active:
                return # Already left

            now = timezone.now()
            
            # Calculate duration since last join
            last_join = participant.attendance_logs.filter(event_type='join').last()
            if last_join:
                duration = max(0, (now - last_join.timestamp).total_seconds())
                participant.total_duration_seconds += int(duration)
            
            participant.left_at = now
            participant.is_active = False
            participant.save()
            
            MeetingAttendanceLog.objects.create(
                participant=participant,
                event_type='leave'
            )

            # --- TIME LIMIT & TEACHER PRESENCE ENFORCEMENT ---
            from .services import check_and_process_meeting_expiration
            check_and_process_meeting_expiration(meeting)

            # --- AUTO-CLEANUP FOR TEMPORARY MEETINGS ---
            if meeting.meeting_type == 'temporary':
                active_exists = MeetingParticipant.objects.filter(
                    meeting=meeting, 
                    is_active=True
                ).exists()
                
                if not active_exists and meeting.status != 'ended':
                    meeting_code = meeting.meeting_code
                    meeting.delete()
                    logger.info(f"Temporary meeting {meeting_code} deleted via Consumer (last participant left).")
        except Meeting.DoesNotExist:
            pass # No persistence for CAM_* rooms
        except Exception as e:
            logger.error(f"Error recording leave: {e}")

    @database_sync_to_async
    def save_chat_message(self, message):
        from common.utils import get_user_display_name, get_user_avatar_url
        try:
            meeting = Meeting.objects.get(meeting_code=self.meeting_code)
            MeetingChat.objects.create(
                meeting=meeting,
                user=self.user,
                message=message
            )
        except Meeting.DoesNotExist:
            pass # No persistence for CAM_* rooms
        except Exception as e:
            logger.error(f"Error saving chat message: {e}")
            
        return {
            'display_name': get_user_display_name(self.user),
            'pfp_url': get_user_avatar_url(self.user)
        }
