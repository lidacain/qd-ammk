from django.contrib import admin
from django.utils.html import format_html
from .models import (
    HourlyPlan,
    HourlyLineStat,
    HourlyPDIStat,
    EditorsWhitelist,
)

# === Helpers ===
@admin.display(description="Слот")
def slot(obj):
    return f"{obj.start.strftime('%H:%M')}-{obj.end.strftime('%H:%M')}"


# === HourlyPlan ===
@admin.register(HourlyPlan)
class HourlyPlanAdmin(admin.ModelAdmin):
    list_display = ("line", "shift", slot, "effective_from", "value", "created_by", "created_at")
    list_filter = ("line", "shift", "start", "end", "effective_from")
    search_fields = ("line",)
    date_hierarchy = "effective_from"
    ordering = ("line", "shift", "start", "-effective_from")
    autocomplete_fields = ("created_by",)
    # Можно быстро править план прямо в списке
    list_editable = ("value",)


# === HourlyLineStat ===
@admin.register(HourlyLineStat)
class HourlyLineStatAdmin(admin.ModelAdmin):
    list_display = (
        "date", "line", "shift", slot, "plan_snapshot", "actual", "downtime_min",
        "downtime_reason", "reason_author",
    )
    list_filter = ("date", "line", "shift")
    search_fields = ("downtime_reason",)
    date_hierarchy = "date"
    ordering = ("-date", "line", "shift", "start")
    # Факт и простой считаются автоматически во вью — делаем их только для чтения
    readonly_fields = ("plan_snapshot", "actual", "downtime_min", "created_at", "created_by")
    autocomplete_fields = ("reason_author", "created_by")


# === HourlyPDIStat ===
@admin.register(HourlyPDIStat)
class HourlyPDIStatAdmin(admin.ModelAdmin):
    list_display = ("date", "shift", slot, "in_count", "out_count", "wip_count", "created_by", "created_at")
    list_filter = ("date", "shift")
    date_hierarchy = "date"
    ordering = ("-date", "shift", "start")
    readonly_fields = ("created_at", "created_by")
    autocomplete_fields = ("created_by",)


# === EditorsWhitelist ===
@admin.register(EditorsWhitelist)
class EditorsWhitelistAdmin(admin.ModelAdmin):
    filter_horizontal = ("users",)
    list_display = ("users_count",)

    @admin.display(description="Пользователей")
    def users_count(self, obj):
        return obj.users.count()
