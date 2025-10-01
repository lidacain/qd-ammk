import csv
from django.http import HttpResponse
from django.contrib import admin
from .models import (
    QRRInvestigation,
    InvestigationFactor,
    FactorCheck,
    InvestigationRequest,
    InvestigationResponsibility,
    QRRResponsible,
)


# === Shared admin helpers ===
def export_as_csv_action(description="Export selected to CSV"):
    def export_as_csv(modeladmin, request, queryset):
        meta = modeladmin.model._meta
        # pick only simple fields
        field_names = [f.name for f in meta.fields]
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{meta.model_name}_export.csv"'
        writer = csv.writer(response)
        writer.writerow(field_names)
        for obj in queryset:
            row = []
            for field in field_names:
                val = getattr(obj, field, "")
                row.append(val if not callable(val) else val())
            writer.writerow(row)
        return response
    export_as_csv.short_description = description
    return export_as_csv

class BaseListAdmin(admin.ModelAdmin):
    """Common list tuning for comfort."""
    list_per_page = 50
    save_on_top = True
    actions = [export_as_csv_action()]


# 🔹 Inline-модели (вложенные формы)
class InvestigationFactorInline(admin.TabularInline):
    model = InvestigationFactor
    extra = 0
    show_change_link = True


class FactorCheckInline(admin.TabularInline):
    model = FactorCheck
    extra = 0
    show_change_link = True


class InvestigationRequestInline(admin.TabularInline):
    model = InvestigationRequest
    extra = 0
    show_change_link = True


class InvestigationResponsibilityInline(admin.TabularInline):
    model = InvestigationResponsibility
    extra = 0
    show_change_link = True


# 🔸 Основная модель БРД
@admin.register(QRRInvestigation)
class QRRInvestigationAdmin(BaseListAdmin):
    list_display = ("form_number", "vin", "station", "status", "form_date", "created_at")
    list_filter = ("status", "station", ("form_date", admin.DateFieldListFilter), ("created_at", admin.DateFieldListFilter))
    search_fields = ("vin", "form_number", "station", "performed_by_name", "confirmed_by_name")
    date_hierarchy = "form_date"
    ordering = ("-created_at", "-form_date")
    list_select_related = False  # keep safe if there are no FKs
    fieldsets = (
        ("Основное", {
            "fields": ("form_number", "vin", "station", "status", "form_date")
        }),
        ("Исполнители", {
            "fields": ("performed_by_name", "confirmed_by_name"),
            "classes": ("collapse",),
        }),
        ("Служебные метки", {
            "fields": ("created_at", "submitted_at", "confirmed_at"),
        }),
    )

    inlines = [
        InvestigationFactorInline,
        FactorCheckInline,
        InvestigationRequestInline,
        InvestigationResponsibilityInline,
    ]

    readonly_fields = ("created_at", "submitted_at", "confirmed_at")


# 🔸 Также отдельно можно зарегистрировать дочерние модели, если нужно
@admin.register(InvestigationFactor)
class InvestigationFactorAdmin(BaseListAdmin):
    list_display = ("investigation", "category", "description")
    list_filter = ("category",)
    search_fields = ("description", "category", "investigation__vin", "investigation__form_number")


@admin.register(FactorCheck)
class FactorCheckAdmin(BaseListAdmin):
    list_display = ("investigation", "factor_text", "result", "date")
    list_filter = (("date", admin.DateFieldListFilter), "result")
    search_fields = ("factor_text", "investigation__vin", "investigation__form_number")
    date_hierarchy = "date"
    ordering = ("-date",)


@admin.register(InvestigationRequest)
class InvestigationRequestAdmin(BaseListAdmin):
    list_display = ("investigation", "factor", "action", "responsible", "date")
    list_filter = (("date", admin.DateFieldListFilter),)
    search_fields = ("action", "responsible", "factor__description", "investigation__vin", "investigation__form_number")
    date_hierarchy = "date"
    ordering = ("-date",)


@admin.register(InvestigationResponsibility)
class InvestigationResponsibilityAdmin(BaseListAdmin):
    list_display = ("investigation", "factor", "department", "full_name", "crcr_number")
    list_filter = ("department",)
    search_fields = ("full_name", "department", "crcr_number", "investigation__vin", "investigation__form_number")


@admin.register(QRRResponsible)
class QRRResponsibleAdmin(BaseListAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)






