import json
from channels.generic.websocket import AsyncWebsocketConsumer


class ActivityLogConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("activity_logs", self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'message': 'WebSocket connected!'
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("activity_logs", self.channel_name)

    async def new_activity_log(self, event):
        await self.send(text_data=json.dumps(event["log"]))
