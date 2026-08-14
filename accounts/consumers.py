import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close()
        else:
            self.user_id = self.scope["user"].id
            self.group_name = f"user_{self.user_id}"
            
            # Join user-specific group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            
            # Join global notifications group
            await self.channel_layer.group_add(
                "public_notifications",
                self.channel_name
            )
            
            await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            await self.channel_layer.group_discard(
                "public_notifications",
                self.channel_name
            )

    # Receive message from room group
    async def send_notification(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps(event["data"]))

    async def new_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_message',
            'data': event['data']
        }))

    async def meeting_started(self, event):
        await self.send(text_data=json.dumps({
            'type': 'meeting_started',
            'data': event['data']
        }))
