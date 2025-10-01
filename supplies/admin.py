from django.contrib import admin
from .models import (
    ContainerUnloadingZone2Inspection,
    ContainerUnloadingZoneSBInspection,
    Post,
    Detail,
    Defect,
    TraceData,
    DefectGrade,
    DefectResponsible,
    BodyDetail,
)

from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html
import csv


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "created_at")
    search_fields = ("name", "location")
    list_filter = (("created_at", admin.DateFieldListFilter), "location")
    ordering = ("name",)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="posts.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["name", "location", "created_at"])
        for o in queryset:
            writer.writerow([
                o.name or "",
                o.location or "",
                o.created_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(o, 'created_at', None) else "",
            ])
        return response


@admin.register(ContainerUnloadingZone2Inspection)
class ContainerUnloadingZone2InspectionAdmin(admin.ModelAdmin):
    list_display = ("post", "controller_link", "container_number", "created_at")
    search_fields = ("post__name", "controller__username", "container_number")
    list_filter = (("created_at", admin.DateFieldListFilter), "controller", "post")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description="Контроллер", ordering="controller__username")
    def controller_link(self, obj):
        if not getattr(obj, 'controller_id', None):
            return "-"
        url = reverse("admin:users_customuser_change", args=[obj.controller_id])
        return format_html('<a href="{}">{}</a>', url, obj.controller.get_username())

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="zone2_inspections.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["post", "controller", "container_number", "created_at"])
        for o in queryset:
            writer.writerow([
                getattr(o.post, 'name', ''),
                o.controller.get_username() if getattr(o, 'controller_id', None) else "",
                o.container_number or "",
                o.created_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(o, 'created_at', None) else "",
            ])
        return response


@admin.register(ContainerUnloadingZoneSBInspection)
class ContainerUnloadingZoneSBInspectionAdmin(admin.ModelAdmin):
    list_display = ("container_number", "container_status_badge", "created_at")
    search_fields = ("container_number",)
    list_filter = ("container_status", ("created_at", admin.DateFieldListFilter))
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description="Статус")
    def container_status_badge(self, obj):
        status = (obj.container_status or "").strip()
        color = "#16a34a" if status.lower() in ("не поврежден", "не повреждён", "ok", "good") else "#ef4444" if status else "#6b7280"
        label = status or "—"
        return format_html('<span style="padding:2px 8px;border-radius:999px;border:1px solid {0};color:{0}">{1}</span>', color, label)

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="sb_inspections.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["container_number", "container_status", "created_at"])
        for o in queryset:
            writer.writerow([
                o.container_number or "",
                o.container_status or "",
                o.created_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(o, 'created_at', None) else "",
            ])
        return response


@admin.register(Detail)
class DetailAdmin(admin.ModelAdmin):
    list_display = ("name", "posts_count")
    search_fields = ("name",)
    filter_horizontal = ("posts",)
    ordering = ("name",)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description="Постов")
    def posts_count(self, obj):
        try:
            return obj.posts.count()
        except Exception:
            return 0

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="details.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["name", "posts_count"])
        for o in queryset:
            writer.writerow([o.name or "", getattr(o.posts, 'count', lambda:0)()])
        return response


@admin.register(Defect)
class DefectAdmin(admin.ModelAdmin):
    list_display = ("name", "posts_count")
    search_fields = ("name",)
    filter_horizontal = ("posts",)
    ordering = ("name",)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description="Постов")
    def posts_count(self, obj):
        try:
            return obj.posts.count()
        except Exception:
            return 0

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="defects.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["name", "posts_count"])
        for o in queryset:
            writer.writerow([o.name or "", getattr(o.posts, 'count', lambda:0)()])
        return response


@admin.register(DefectGrade)
class DefectGradeAdmin(admin.ModelAdmin):
    list_display = ("name", "description_short")
    search_fields = ("name", "description")
    ordering = ("name",)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description="Описание")
    def description_short(self, obj):
        if not obj.description:
            return "-"
        return obj.description if len(obj.description) <= 60 else obj.description[:60] + "…"

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="defect_grades.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["name", "description"])
        for o in queryset:
            writer.writerow([o.name or "", o.description or ""])
        return response


@admin.register(DefectResponsible)
class DefectResponsibleAdmin(admin.ModelAdmin):
    list_display = ("name", "department_badge", "posts_count")
    search_fields = ("name", "department")
    filter_horizontal = ("posts",)
    ordering = ("name",)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description="Отдел")
    def department_badge(self, obj):
        if not obj.department:
            return "-"
        return format_html('<span style="padding:2px 8px;border-radius:6px;border:1px solid #3b82f6;color:#3b82f6">{}</span>', obj.department)

    @admin.display(description="Постов")
    def posts_count(self, obj):
        try:
            return obj.posts.count()
        except Exception:
            return 0

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="defect_responsibles.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["name", "department", "posts_count"])
        for o in queryset:
            writer.writerow([o.name or "", o.department or "", getattr(o.posts, 'count', lambda:0)()])
        return response


@admin.register(TraceData)
class TraceDataAdmin(admin.ModelAdmin):
    list_display = ("brand", "model", "vin_rk", "butch_number", "engine_number", "body_color", "date_added")
    search_fields = ("brand", "model", "vin_rk", "butch_number", "engine_number", "body_color")
    list_filter = ("brand", "model", ("date_added", admin.DateFieldListFilter), "butch_number", "body_color")
    ordering = ("-date_added",)
    date_hierarchy = "date_added"
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="trace_data.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["brand", "model", "vin_rk", "butch_number", "engine_number", "body_color", "date_added"])
        for o in queryset:
            writer.writerow([
                o.brand or "", o.model or "", o.vin_rk or "", o.engine_number or "", o.body_color or "",
                o.date_added.strftime("%Y-%m-%d %H:%M:%S") if getattr(o, 'date_added', None) else "",
            ])
        return response


@admin.register(BodyDetail)
class BodyDetailAdmin(admin.ModelAdmin):
    list_display = ("name", "zone_badge", "posts_count")
    list_filter = ("zone",)
    search_fields = ("name",)
    filter_horizontal = ("posts",)
    ordering = ("name",)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description="Зона")
    def zone_badge(self, obj):
        if not obj.zone:
            return "-"
        return format_html('<span style="padding:2px 8px;border-radius:6px;border:1px solid #0ea5e9;color:#0ea5e9">{}</span>', obj.zone)

    @admin.display(description="Постов")
    def posts_count(self, obj):
        try:
            return obj.posts.count()
        except Exception:
            return 0

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="body_details.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["name", "zone", "posts_count"])
        for o in queryset:
            writer.writerow([o.name or "", o.zone or "", getattr(o.posts, 'count', lambda:0)()])
        return response