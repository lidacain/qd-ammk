from .models import UserActivityLog
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils.timezone import now
from datetime import timedelta
from django.utils.formats import date_format
from django.utils.timezone import localtime


class ActivityLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        excluded_paths = [
            '/admin',
            '/secure-admin-lidacain',
            '/administrators',
        ]

        is_excluded_path = (
            'get-notifications' in request.path
            or any(request.path.startswith(path) for path in excluded_paths)
        )

        user = request.user if request.user.is_authenticated else None
        is_lidacain_user = user.username.lower().find('lidacain') != -1 if user else False

        if not is_excluded_path and not is_lidacain_user:
            ip = request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('REMOTE_ADDR')
            if ip and ',' in ip:
                ip = ip.split(',')[0].strip()

            role = getattr(user, 'role', '') if user else ''
            url = request.build_absolute_uri()
            if url and len(url) > 1000:
                url = url[:1000]

            # 🔒 Проверка на дубль
            recent = now() - timedelta(seconds=5)
            if UserActivityLog.objects.filter(user=user, url=url, timestamp__gte=recent).exists():
                return response

            log = UserActivityLog.objects.create(
                user=user,
                ip_address=ip,
                url=url,
                role=role
            )

            # WebSocket push
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "activity_logs",
                {
                    "type": "new_activity_log",  # или send_new_log
                    "log": {
                        "ip_address": log.ip_address,
                        "username": log.user.username if log.user else "",
                        "full_name": f"{log.user.last_name} {log.user.first_name}" if log.user else "-",
                        "role": log.role,
                        "url": log.url,
                        "timestamp": date_format(localtime(log.timestamp), format="j E Y г. H:i", use_l10n=True),
                    }
                }
            )

        return response