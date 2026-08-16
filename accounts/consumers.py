import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        user = self.scope.get("user")
        if user and not user.is_anonymous:
            self.user_id = user.id
            self.group_name = f"user_{self.user_id}"
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
        else:
            self.group_name = "user_anonymous"

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

    async def identity_updated(self, event):
        await self.send(text_data=json.dumps({
            'type': 'identity_updated',
            'data': event['data']
        }))
