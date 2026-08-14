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
            self.user = self.scope['user']
            
            if not self.user.is_authenticated:
                await self.close()
                return

            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            # Record join and get user meta in one go
            user_data = await self.get_user_meta()

            # Track for CAM_* rooms
            if self.meeting_code.startswith('CAM_'):
                if self.meeting_code not in cam_room_participants:
                    cam_room_participants[self.meeting_code] = {}
                cam_room_participants[self.meeting_code][self.user.id] = self.user.username
            
            # Get other active participants BEFORE accepting to ensure we have them
            active_participants = await self.get_active_participants()
            
            await self.accept()

            # Send current participant list to the joiner
            await self.send(text_data=json.dumps({
                'type': 'participant_list',
                'participants': active_participants
            }))

            # Notify others that user joined
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_joined',
                    'user_id': user_data['id'],
                    'username': user_data['username'],
                    'is_host': user_data['is_host'],
                    'is_admin': user_data['is_admin'],
                }
            )
        except Exception as e:
            # Avoid using self.user directly in strings to prevent DB access errors
            logger.error(f"WS Connect Error: {str(e)}")
            await self.close()

    @database_sync_to_async
    def get_user_meta(self):
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
                'is_host': meeting.teacher == self.user or self.user.is_superuser,
                'is_admin': self.user.is_superuser
            }
        except Meeting.DoesNotExist:
             # Handle CAM_* rooms for live lectures
             if self.meeting_code.startswith('CAM_'):
                 camera_id = self.meeting_code.split('_')[1]
                 is_host = False
                 try:
                     camera = Camera.objects.get(id=camera_id)
                     is_host = (camera.live_teacher == self.user) or self.user.is_superuser
                 except Exception as e:
                     logger.warning(f"Error checking camera host status: {e}")
                     
                 return {
                     'id': self.user.id,
                     'username': self.user.username,
                     'is_host': is_host,
                     'is_admin': self.user.is_superuser
                 }
             raise

    @database_sync_to_async
    def get_active_participants(self):
        try:
            meeting = Meeting.objects.get(meeting_code=self.meeting_code)
            # Find all users who are marked active in this meeting, excluding self
            active = MeetingParticipant.objects.filter(
                meeting=meeting, 
                is_active=True
            ).exclude(user=self.user).select_related('user')
            
            return [
                {
                    'user_id': p.user.id,
                    'username': p.user.username,
                    'is_host': meeting.teacher == p.user or p.user.is_superuser,
                    'is_admin': p.user.is_superuser
                } for p in active
            ]
        except Meeting.DoesNotExist:
            if self.meeting_code.startswith('CAM_'):
                # Return from in-memory tracking
                participants = cam_room_participants.get(self.meeting_code, {})
                return [
                    {'user_id': uid, 'username': uname, 'is_host': False, 'is_admin': False}
                    for uid, uname in participants.items()
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
                    await self.save_chat_message(data['message'])
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'chat_message',
                            'message': data['message'],
                            'username': self.user.username,
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
        except Exception as e:
            logger.error(f"Receive error: {e}")
    
    async def user_joined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_joined',
            'user_id': event['user_id'],
            'username': event['username'],
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

            # --- AUTO-CLEANUP FOR TEMPORARY MEETINGS ---
            if meeting.meeting_type == 'temporary':
                active_exists = MeetingParticipant.objects.filter(
                    meeting=meeting, 
                    is_active=True
                ).exists()
                
                if not active_exists:
                    meeting_code = meeting.meeting_code
                    meeting.delete()
                    logger.info(f"Temporary meeting {meeting_code} deleted via Consumer (last participant left).")
        except Meeting.DoesNotExist:
            pass # No persistence for CAM_* rooms
        except Exception as e:
            logger.error(f"Error recording leave: {e}")

    @database_sync_to_async
    def save_chat_message(self, message):
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
