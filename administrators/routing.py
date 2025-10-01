from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path("ws/activity-logs/", consumers.ActivityLogConsumer.as_asgi()),
]