# vehicle_history/urls.py
from django.urls import path
from . import views

app_name = "vehicle_history"

urlpatterns = [
    path('export_excel_all/', views.export_all_vin_histories_to_excel, name='export_excel_all'),
    path('incoming/export_excel/body_inspection/', views.export_body_inspection_excel, name='export_body_inspection_excel'),
    path('incoming/export_excel/parts_acceptance/', views.export_parts_acceptance_excel, name='export_parts_acceptance_excel'),
    path('incoming/export_excel/final_acceptance/', views.export_final_acceptance_excel, name='export_final_acceptance_excel'),
    path('incoming/export/photos/', views.export_incoming_photos_zip, name='export_incoming_photos_zip'),
    path("assembly/export-excel/", views.export_assembly_excel, name="export_assembly_excel"),
    path('incoming/export_excel/containers_acceptance/', views.export_containers_acceptance_excel, name='export_containers_acceptance_excel'),
]
