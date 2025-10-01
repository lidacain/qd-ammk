# factory_server/asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "factory_server.settings")

# HTTP-приложение (Django)
django_asgi_app = get_asgi_application()

# Собираем WebSocket-маршруты из приложений
websocket_urlpatterns = []

# administrators.routing.websocket_urlpatterns (если файла нет — тихо пропустим)
try:
    from administrators.routing import websocket_urlpatterns as admin_ws
    websocket_urlpatterns += admin_ws
except Exception:
    pass

# Если будут другие приложения с WS — добавляй аналогично:
# try:
#     from users.routing import websocket_urlpatterns as users_ws
#     websocket_urlpatterns += users_ws
# except Exception:
#     pass

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})

