from django.contrib import admin
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html
import csv
from .models import UserActivityLog


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user_link", "role_badge", "ip_address", "url_short")
    list_filter = ("role", ("timestamp", admin.DateFieldListFilter), "user")
    search_fields = ("ip_address", "user__username", "url")
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)
    readonly_fields = ("user", "ip_address", "role", "url", "timestamp")
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description="Пользователь", ordering="user__username")
    def user_link(self, obj):
        if not getattr(obj, "user_id", None):
            return "-"
        url = reverse("admin:users_customuser_change", args=[obj.user_id])
        label = obj.user.get_username()
        return format_html('<a href="{}">{}</a>', url, label)

    @admin.display(description="Роль")
    def role_badge(self, obj):
        role = (obj.role or "").strip()
        color = "#2563eb"  # синий по умолчанию
        if role.lower() in ("admin", "administrator", "superuser"):
            color = "#f97316"  # оранжевый
        elif role.lower() in ("manager", "moderator"):
            color = "#16a34a"  # зелёный
        elif role.lower() in ("staff",):
            color = "#6b7280"  # серый
        return format_html('<span style="padding:2px 8px;border-radius:999px;border:1px solid {0};color:{0}">{1}</span>', color, role or "—")

    @admin.display(description="URL")
    def url_short(self, obj):
        if not obj.url:
            return "—"
        text = obj.url
        if len(text) > 60:
            text = text[:60] + "…"
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', obj.url, text)

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="user_activity_logs.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["timestamp", "user", "role", "ip_address", "url"])
        for o in queryset:
            writer.writerow([
                o.timestamp.strftime("%Y-%m-%d %H:%M:%S") if getattr(o, 'timestamp', None) else "",
                o.user.get_username() if getattr(o, 'user_id', None) else "",
                o.role or "",
                o.ip_address or "",
                o.url or "",
            ])
        return response

    def has_add_permission(self, request):
        return False  # Запрет на добавление через админку

    def has_change_permission(self, request, obj=None):
        return False  # Запрет на редактирование

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # Только суперпользователи могут удалять логи
