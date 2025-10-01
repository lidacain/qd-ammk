from django.urls import path
from .views import offtake_table_view, plan_editor_view, pdi_table_view


app_name = "line_stats"
urlpatterns = [
    path("offtake/", offtake_table_view, name="offtake"),
    path("plan/",    plan_editor_view,   name="plan_editor"),
    path("pdi/",     pdi_table_view,     name="pdi"),
]