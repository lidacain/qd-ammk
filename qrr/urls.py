from django.urls import path
from .views import qrr_dashboard, qrr_blank_list, create_qrr_blank, qrr_blank_create, qrr_defects_board, api_qrr_set_defect_responsible, api_qrr_change_defect_grade, api_qrr_set_defect_responsible_bulk


urlpatterns = [
    path('dashboard/', qrr_dashboard, name='qrr_dashboard'),
    path("blanks/", qrr_blank_list, name="qrr_blank_list"),
    path("blanks/create/", create_qrr_blank, name="create_qrr_blank"),
    path('blanks/create/', qrr_blank_create, name='qrr_blank_create'),
    path("defects/board/", qrr_defects_board, name="qrr_defects_board"),
    path("api/defect/set-responsible/", api_qrr_set_defect_responsible, name="api_qrr_set_defect_responsible"),
    path("api/defect/set-responsible-bulk/", api_qrr_set_defect_responsible_bulk, name="api_qrr_set_defect_responsible_bulk"),
    path("api/defect/change-grade/", api_qrr_change_defect_grade, name="api_qrr_change_defect_grade"),
]
