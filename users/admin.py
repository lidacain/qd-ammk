from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.models import Group, Permission
from .models import CustomUser, HelpdeskContact, Notification, Employee, Selection, ExportHistory, OvertimeRecord, KTVDefect
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.contrib import admin, messages
from django.db.models import F
from django.db.models.functions import TruncDate
from django.utils.html import format_html
from django.utils.timezone import now
from django.http import HttpResponse
import csv
from datetime import date, timedelta

# --- Enable autocomplete for Groups & Permissions ---
class CustomGroupAdmin(GroupAdmin):
    search_fields = ("name",)

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    search_fields = ("name", "codename", "content_type__app_label", "content_type__model")
    list_display = ("name", "codename", "content_type")
    list_select_related = ("content_type",)

# Re-register Group with our searchable admin (safe if not previously registered)
try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass
admin.site.register(Group, CustomGroupAdmin)



@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    autocomplete_fields = ["groups", "user_permissions"]
    filter_horizontal = ()

    # теперь username тоже кликабелен
    list_display = (
        "avatar_preview", "username_link", "last_name", "first_name",
        "position", "role", "is_staff", "is_active"
    )
    list_filter = ("role", "is_staff", "is_active")

    def avatar_preview(self, obj):
        if obj.avatar:
            return format_html(
                '<img src="{}" style="width: 40px; height: 40px; border-radius: 50%;" />',
                obj.avatar.url
            )
        return format_html('<span style="color: gray;">Нет</span>')
    avatar_preview.short_description = "Аватар"

    def username_link(self, obj):
        url = reverse("admin:users_customuser_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.username)
    username_link.short_description = "Имя пользователя"
    username_link.admin_order_field = "username"

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Персональная информация", {
            "fields": ("last_name", "first_name", "patronymic", "position", "email", "avatar")
        }),
        ("Роли и разрешения", {
            "fields": ("role", "is_staff", "is_active", "is_superuser", "groups", "user_permissions")
        }),
        ("Даты", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "username", "password1", "password2", "last_name", "first_name",
                "patronymic", "position", "email", "avatar", "role", "is_staff", "is_active"
            ),
        }),
    )

    search_fields = ("username", "email", "first_name", "last_name", "patronymic")
    ordering = ("username",)

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="users.csv"'
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["username", "last_name", "first_name", "patronymic", "position", "email", "role", "is_staff", "is_active"])
        for u in queryset:
            writer.writerow([
                u.username, u.last_name or "", u.first_name or "", u.patronymic or "",
                u.position or "", u.email or "", u.role or "", "1" if u.is_staff else "0", "1" if u.is_active else "0"
            ])
        return response

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)


@admin.register(HelpdeskContact)
class HelpdeskContactAdmin(admin.ModelAdmin):
    list_display = ("employee_name", "position", "department_badge", "phone_number", "email")
    search_fields = ("employee_name", "position", "department", "phone_number", "email")
    list_filter = ("department",)
    ordering = ("employee_name",)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description="Отдел")
    def department_badge(self, obj):
        if not obj.department:
            return "-"
        return format_html('<span style="padding:2px 8px;border-radius:6px;border:1px solid #3b82f6;color:#3b82f6">{}</span>', obj.department)

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="helpdesk_contacts.csv"'
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["employee_name", "position", "department", "phone_number", "email"])
        for o in queryset:
            writer.writerow([
                o.employee_name or "", o.position or "", o.department or "", o.phone_number or "", o.email or "",
            ])
        return response


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient_link", "message_short", "vin_number", "defect", "is_read_badge", "created_at")
    search_fields = ("recipient__username", "recipient__first_name", "recipient__last_name", "message", "vin_number", "defect")
    list_filter = ("is_read", ("created_at", admin.DateFieldListFilter))
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    save_on_top = True
    actions = ("mark_as_read", "mark_as_unread", "export_csv",)

    @admin.display(description="Получатель", ordering="recipient__username")
    def recipient_link(self, obj):
        url = reverse("admin:users_customuser_change", args=[obj.recipient_id]) if obj.recipient_id else "#"
        label = obj.recipient.get_username() if obj.recipient_id else "-"
        return format_html('<a href="{}">{}</a>', url, label)

    @admin.display(description="Сообщение")
    def message_short(self, obj):
        if not obj.message:
            return "-"
        text = obj.message.replace("\n", " ")
        return text if len(text) <= 60 else text[:60] + "…"

    @admin.display(description="Статус")
    def is_read_badge(self, obj):
        if obj.is_read:
            return format_html('<span style="padding:2px 8px;border-radius:999px;border:1px solid #16a34a;color:#16a34a">прочитано</span>')
        return format_html('<span style="padding:2px 8px;border-radius:999px;border:1px solid #ef4444;color:#ef4444">не прочитано</span>')

    @admin.action(description="Отметить как прочитанные")
    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f"Обновлено записей: {updated}", messages.SUCCESS)

    @admin.action(description="Отметить как не прочитанные")
    def mark_as_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f"Обновлено записей: {updated}", messages.INFO)

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="notifications.csv"'
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["recipient", "message", "vin_number", "defect", "is_read", "created_at"])
        for o in queryset:
            writer.writerow([
                o.recipient.get_username() if o.recipient_id else "",
                (o.message or "").replace("\n", " "),
                o.vin_number or "",
                o.defect or "",
                "1" if o.is_read else "0",
                o.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            ])
        return response


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("name", "position", "department_badge", "created_at", "updated_at")
    search_fields = ("name", "position", "department")
    list_filter = ("department", ("created_at", admin.DateFieldListFilter))
    ordering = ("name",)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description="Отдел")
    def department_badge(self, obj):
        if not obj.department:
            return "-"
        return format_html('<span style="padding:2px 8px;border-radius:6px;border:1px solid #3b82f6;color:#3b82f6">{}</span>', obj.department)

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="employees.csv"'
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["name", "position", "department", "created_at", "updated_at"])
        for o in queryset:
            writer.writerow([
                o.name or "", o.position or "", o.department or "",
                o.created_at.strftime("%Y-%m-%d %H:%M:%S") if o.created_at else "",
                o.updated_at.strftime("%Y-%m-%d %H:%M:%S") if o.updated_at else "",
            ])
        return response


@admin.register(Selection)
class SelectionAdmin(admin.ModelAdmin):
    list_display = ("employee", "manager_link", "selected_date", "created_at")
    search_fields = ("employee__name", "manager__username", "manager__first_name", "manager__last_name")
    list_filter = (("selected_date", admin.DateFieldListFilter), "manager")
    ordering = ("-selected_date",)
    date_hierarchy = "selected_date"
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description="Менеджер", ordering="manager__username")
    def manager_link(self, obj):
        if not obj.manager_id:
            return "-"
        url = reverse("admin:users_customuser_change", args=[obj.manager_id])
        return format_html('<a href="{}">{}</a>', url, obj.manager.get_username())

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="selections.csv"'
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["employee", "manager", "selected_date", "created_at"])
        for o in queryset:
            writer.writerow([
                o.employee.name if o.employee_id else "",
                o.manager.get_username() if o.manager_id else "",
                o.selected_date.isoformat() if o.selected_date else "",
                o.created_at.strftime("%Y-%m-%d %H:%M:%S") if o.created_at else "",
            ])
        return response


@admin.register(ExportHistory)
class ExportHistoryAdmin(admin.ModelAdmin):
    list_display = ("file_name", "manager_link", "export_date", "record_count_badge")
    search_fields = ("file_name", "manager__username")
    list_filter = (("export_date", admin.DateFieldListFilter),)
    ordering = ("-export_date",)
    date_hierarchy = "export_date"
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description="Менеджер", ordering="manager__username")
    def manager_link(self, obj):
        if not obj.manager_id:
            return "-"
        url = reverse("admin:users_customuser_change", args=[obj.manager_id])
        return format_html('<a href="{}">{}</a>', url, obj.manager.get_username())

    @admin.display(description="Записей")
    def record_count_badge(self, obj):
        try:
            n = int(obj.record_count)
        except Exception:
            n = 0
        return format_html('<span style="padding:2px 8px;border-radius:999px;border:1px solid #6b7280;color:#6b7280">{}</span>', n)

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="export_history.csv"'
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["file_name", "manager", "export_date", "record_count"])
        for o in queryset:
            writer.writerow([
                o.file_name or "",
                o.manager.get_username() if o.manager_id else "",
                o.export_date.strftime("%Y-%m-%d %H:%M:%S") if o.export_date else "",
                o.record_count or 0,
            ])
        return response


@admin.register(OvertimeRecord)
class OvertimeRecordAdmin(admin.ModelAdmin):
    list_display = (
        'employee_name', 'date', 'start_time', 'end_time', 'hours',
        'is_xtk_badge', 'justification_short', 'compensated_day',
        'added_by_link', 'created_at'
    )
    list_filter = ('compensated_day', ("date", admin.DateFieldListFilter), 'added_by')
    search_fields = ('employee__name', 'employee__position', 'justification', 'added_by__username')
    date_hierarchy = 'date'
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-date',)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    # Отображение полного имени сотрудника и должности
    def employee_name(self, obj):
        return f"{obj.employee.name} ({obj.employee.position})"
    employee_name.short_description = "Сотрудник"

    # Укорачиваем длинное обоснование
    def justification_short(self, obj):
        if obj.justification:
            return (obj.justification[:50] + '...') if len(obj.justification) > 50 else obj.justification
        return "-"
    justification_short.short_description = "Обоснование"

    @admin.display(description="ХТК")
    def is_xtk_badge(self, obj):
        if obj.is_xtk:
            return format_html('<span style="padding:2px 8px;border-radius:999px;border:1px solid #0ea5e9;color:#0ea5e9">ХТК</span>')
        return "-"

    @admin.display(description="Добавил", ordering="added_by__username")
    def added_by_link(self, obj):
        if not obj.added_by_id:
            return "-"
        url = reverse("admin:users_customuser_change", args=[obj.added_by_id])
        return format_html('<a href="{}">{}</a>', url, obj.added_by.get_username())

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="overtime_records.csv"'
        writer = csv.writer(response, delimiter=";")
        writer.writerow([
            'employee', 'position', 'date', 'start_time', 'end_time', 'hours',
            'is_xtk', 'justification', 'compensated_day', 'added_by', 'created_at'
        ])
        for o in queryset:
            writer.writerow([
                o.employee.name if o.employee_id else "",
                o.employee.position if o.employee_id else "",
                o.date.isoformat() if o.date else "",
                o.start_time.strftime('%H:%M') if o.start_time else "",
                o.end_time.strftime('%H:%M') if o.end_time else "",
                o.hours if o.hours is not None else "",
                "1" if o.is_xtk else "0",
                (o.justification or "").replace("\n", " "),
                "1" if o.compensated_day else "0",
                o.added_by.get_username() if o.added_by_id else "",
                o.created_at.strftime("%Y-%m-%d %H:%M:%S") if o.created_at else "",
            ])
        return response


# --- Пользовательский фильтр по статусу показа ---
class VisibilityStatusFilter(admin.SimpleListFilter):
    title = "Статус показа"
    parameter_name = "visibility"

    def lookups(self, request, model_admin):
        return [
            ("active", "Активно (видно уже)"),
            ("scheduled", "Запланировано (дата в будущем)"),
            ("overdue", "Просрочено (дата раньше чем создано)"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(visible_from__lte=date.today())
        if self.value() == "scheduled":
            return queryset.filter(visible_from__gt=date.today())
        if self.value() == "overdue":
            # visible_from earlier than the creation date (by date)
            qs = queryset.annotate(created_date=TruncDate("created_at"))
            return qs.filter(visible_from__lt=F("created_date"))
        return queryset


# --- Админ-форма (удобные виджеты/валидация) ---
from django import forms

class KTVDefectAdminForm(forms.ModelForm):
    class Meta:
        model = KTVDefect
        fields = "__all__"
        widgets = {
            "visible_from": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        # Мягкая проверка: если visible_from сильно в прошлом — предупредим
        vf = cleaned.get("visible_from")
        if vf and vf < date(2000, 1, 1):
            self.add_error("visible_from", "Слишком старая дата.")
        return cleaned


@admin.register(KTVDefect)
class KTVDefectAdmin(admin.ModelAdmin):
    form = KTVDefectAdminForm

    list_select_related = ("created_by",)
    autocomplete_fields = ("created_by",)

    # Главное представление
    list_display = (
        "colored_table_type",
        "detail",
        "defect",
        "grade",
        "count",
        "visible_from_badge",
        "created_at",
        "created_by",
    )
    list_display_links = ("detail", "defect")
    list_editable = ("count",)  # мгновенное правка количества в списке
    list_filter = (
        "table_type",
        "grade",
        VisibilityStatusFilter,
        ("visible_from", admin.DateFieldListFilter),
        ("created_at", admin.DateFieldListFilter),
        "created_by",
    )
    search_fields = ("detail", "defect", "grade", "comment")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50
    save_on_top = True

    # Разбиение по секциям в форме
    fieldsets = (
        ("Источник и предмет", {
            "fields": ("table_type", "detail", "defect", "grade", "count")
        }),
        ("Планирование показа", {
            "fields": ("visible_from",),
            "description": "С какой даты запись должна быть видна на витрине/в отчётах."
        }),
        ("Служебное", {
            "fields": ("comment", "created_by", "created_at"),
        }),
    )
    readonly_fields = ("created_at",)

    # Красивые колонки
    @admin.display(description="Таблица")
    def colored_table_type(self, obj: KTVDefect):
        color = "#3b82f6" if obj.table_type == "by_grades" else "#f59e0b"
        text = "По грейдам" if obj.table_type == "by_grades" else "По массовости"
        return format_html(
            '<span style="padding:2px 8px;border-radius:999px;'
            'font-weight:600;background:rgba(0,0,0,.03);'
            f'border:1px solid {color};color:{color}">{text}</span>'
        )

    @admin.display(description="Показывать с")
    def visible_from_badge(self, obj: KTVDefect):
        today = date.today()
        if obj.visible_from > today:
            color, label = "#0ea5e9", "запланировано"
        elif obj.visible_from <= today:
            color, label = "#16a34a", "активно"
        else:
            color, label = "#ef4444", "ошибка"
        return format_html(
            '<span title="{}" style="padding:2px 8px;border-radius:8px;'
            'border:1px solid {};color:{};">{} · {}</span>',
            obj.visible_from.isoformat(), color, color, obj.visible_from.strftime("%d.%m.%Y"), label
        )

    # Автозаполнение автора
    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    # --- Actions ---
    actions = (
        "make_visible_today",
        "postpone_7",
        "postpone_14",
        "postpone_30",
        "export_csv",
    )

    @admin.action(description="Сделать видимым сегодня")
    def make_visible_today(self, request, queryset):
        updated = queryset.update(visible_from=date.today())
        self.message_user(request, f"Обновлено записей: {updated}", messages.SUCCESS)

    def _postpone(self, request, queryset, days):
        updated = 0
        for obj in queryset:
            obj.visible_from = max(obj.visible_from, date.today()) + timedelta(days=days)
            obj.save(update_fields=["visible_from"])
            updated += 1
        self.message_user(request, f"Отложено на {days} дн.: {updated}", messages.INFO)

    @admin.action(description="Отложить на 7 дней")
    def postpone_7(self, request, queryset): self._postpone(request, queryset, 7)

    @admin.action(description="Отложить на 14 дней")
    def postpone_14(self, request, queryset): self._postpone(request, queryset, 14)

    @admin.action(description="Отложить на 30 дней")
    def postpone_30(self, request, queryset): self._postpone(request, queryset, 30)

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="ktv_defects.csv"'
        writer = csv.writer(response, delimiter=";")
        writer.writerow([
            "table_type", "detail", "defect", "grade", "count",
            "created_at", "visible_from", "comment", "created_by",
        ])
        for o in queryset:
            writer.writerow([
                o.table_type, o.detail, o.defect, o.grade or "",
                o.count, o.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                o.visible_from.isoformat(), (o.comment or "").replace("\n", " "),
                (o.created_by.get_full_name() or o.created_by.username) if o.created_by else "",
            ])
        return response
