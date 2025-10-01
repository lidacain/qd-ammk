from django.contrib import admin
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html
import csv
from .models import PostAssembly, DefectAssembly, AssemblyPart, AssemblyDefect, AssemblyUnit, AssemblyDefectResponsible, AssemblyDefectGrade, AssemblyZone


@admin.register(PostAssembly)
class PostAssemblyAdmin(admin.ModelAdmin):
    """Админка для постов сборки"""
    list_display = ("id", "name", "location", "created_at")
    search_fields = ("name", "location")
    list_filter = (("created_at", admin.DateFieldListFilter), "location")
    ordering = ("name",)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="assembly_posts.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["id", "name", "location", "created_at"])
        for o in queryset:
            writer.writerow([
                o.id,
                o.name or "",
                o.location or "",
                o.created_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(o, 'created_at', None) else "",
            ])
        return response


@admin.register(DefectAssembly)
class DefectAssemblyAdmin(admin.ModelAdmin):
    """Админка для дефектов сборки"""
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
        response["Content-Disposition"] = 'attachment; filename="assembly_defects.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["name", "posts_count"])
        for o in queryset:
            writer.writerow([o.name or "", getattr(o.posts, 'count', lambda:0)()])
        return response


# ✅ Удаляем возможное повторное `admin.site.register(AssemblyPart, AssemblyPartAdmin)`
@admin.register(AssemblyPart)
class AssemblyPartAdmin(admin.ModelAdmin):
    """Админка для узлов/деталей"""
    list_display = ("name", "modification", "size", "min_quantity", "max_quantity", "min_torque", "max_torque")
    search_fields = ("name",)
    list_filter = ("modification", "size")
    ordering = ("name",)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="assembly_parts.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["name", "modification", "size", "min_quantity", "max_quantity", "min_torque", "max_torque"])
        for o in queryset:
            writer.writerow([
                o.name or "", o.modification or "", o.size or "",
                o.min_quantity if getattr(o, 'min_quantity', None) is not None else "",
                o.max_quantity if getattr(o, 'max_quantity', None) is not None else "",
                o.min_torque if getattr(o, 'min_torque', None) is not None else "",
                o.max_torque if getattr(o, 'max_torque', None) is not None else "",
            ])
        return response


@admin.register(AssemblyDefect)
class AssemblyDefectAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'nameENG', 'posts_count')
    search_fields = ('name', 'nameENG')
    filter_horizontal = ('posts',)
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
        response["Content-Disposition"] = 'attachment; filename="assembly_defects_dict.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["id", "name", "nameENG", "posts_count"])
        for o in queryset:
            writer.writerow([o.id, o.name or "", o.nameENG or "", getattr(o.posts, 'count', lambda:0)()])
        return response


@admin.register(AssemblyZone)
class AssemblyZoneAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'posts_count')
    search_fields = ('name',)
    ordering = ('name',)
    filter_horizontal = ('posts',)
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
        response["Content-Disposition"] = 'attachment; filename="assembly_zones.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["id", "name", "posts_count"])
        for o in queryset:
            writer.writerow([o.id, o.name or "", getattr(o.posts, 'count', lambda:0)()])
        return response


@admin.register(AssemblyUnit)
class AssemblyUnitAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'zone_badge', 'posts_count')
    list_filter = ('zone',)
    search_fields = ('name', 'zone__name')
    ordering = ('zone__name', 'name')
    filter_horizontal = ('posts',)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description='Зона')
    def zone_badge(self, obj):
        if not obj.zone:
            return '-'
        return format_html('<span style="padding:2px 8px;border-radius:6px;border:1px solid #0ea5e9;color:#0ea5e9">{}</span>', obj.zone.name)

    @admin.display(description='Постов')
    def posts_count(self, obj):
        try:
            return obj.posts.count()
        except Exception:
            return 0

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="assembly_units.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['id', 'name', 'zone', 'posts_count'])
        for o in queryset:
            writer.writerow([o.id, o.name or '', getattr(o.zone, 'name', ''), getattr(o.posts, 'count', lambda:0)()])
        return response


@admin.register(AssemblyDefectGrade)
class AssemblyDefectGradeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description_short')
    search_fields = ('name', 'description')
    ordering = ('name',)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description='Описание')
    def description_short(self, obj):
        if not obj.description:
            return '-'
        return obj.description if len(obj.description) <= 60 else obj.description[:60] + '…'

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="assembly_defect_grades.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['id', 'name', 'description'])
        for o in queryset:
            writer.writerow([o.id, o.name or '', o.description or ''])
        return response


@admin.register(AssemblyDefectResponsible)
class AssemblyDefectResponsibleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'department_badge', 'posts_count')
    search_fields = ('name', 'department')
    filter_horizontal = ('posts',)
    ordering = ('name',)
    list_per_page = 50
    save_on_top = True
    actions = ("export_csv",)

    @admin.display(description='Отдел')
    def department_badge(self, obj):
        if not obj.department:
            return '-'
        return format_html('<span style="padding:2px 8px;border-radius:6px;border:1px solid #3b82f6;color:#3b82f6">{}</span>', obj.department)

    @admin.display(description='Постов')
    def posts_count(self, obj):
        try:
            return obj.posts.count()
        except Exception:
            return 0

    @admin.action(description="Экспортировать в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="assembly_defect_responsibles.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['id', 'name', 'department', 'posts_count'])
        for o in queryset:
            writer.writerow([o.id, o.name or '', o.department or '', getattr(o.posts, 'count', lambda:0)()])
        return response
