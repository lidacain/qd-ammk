from django.urls import path
from django.shortcuts import redirect
from .views import (
    login_view, logout_view, controller_dashboard, master_dashboard,
    admin_dashboard, post_detail, create_controller, defect_table,
    defect_reports, master_redirect, get_defects, get_defect_stats,
    notifications_view, get_notifications, sb_defect_details_view,
    helpdesk_directory, uud_defect_details_view, incoming_workshop_dashboard,
    assembly_workshop_dashboard, incoming_general_report,

    vin_tracking_select, vin_tracking_view, vin_post_detail,
    vin_tracking_overview, vin_tracking_post_vins, export_vin_excel,
    export_all_defects_excel,
    profile,

    remember_recent_post,

    employee_search, edit_selection, delete_selection, export_excel,
    export_history, load_export_to_selection, re_export_excel,
    edit_export_history, delete_export_history, delete_all_selections,
    office_overview, export_rvd_excel, delete_all_selections_dp,
    export_word_rvd, overtime_overview, assign_day_off, update_day_off,
    export_pending_day_off,

    master_controller_panel, change_controller_password, delete_controller,
    body_inspection_report, body_inspection_table, body_inspection_export, body_inspection_form,
    parts_acceptance_report, parts_acceptance_table, parts_acceptance_export, parts_acceptance_form,
    final_acceptance_report, final_acceptance_table, final_acceptance_export, final_acceptance_form,
    containers_acceptance_table, containers_acceptance_export,
    assembly_current_report, assembly_current_table, assembly_current_export,
    assembly_post_table, assembly_post_manual_entry, assembly_post_report,
    assembly_post_edit, assembly_post_export, delete_entry_view, assembly_general_report,
    download_summary_report,

    manage_post_visibility, assembly_zone_update,assembly_defect_update,assembly_defect_delete,
    assembly_unit_update,assembly_unit_delete,assembly_zone_delete,

    vin_list_view, export_vin_list_excel,

    in_development,


    qrqc_dashboard_view, qrqc_brand_view, defect_details_view,
    ktvdefect_list, ktvdefect_upsert, ktvdefect_delete,


    assembly_counter_dashboard, assembly_counter_api,

    uud_uniq,

    # MES APIs per section
    trim_overview_api, trim_list_api,
    bqa_overview_api, bqa_list_api,
    qa_overview_api, qa_list_api,
    uud_overview_api, uud_list_api,
    ves_overview_api, ves_list_api,
    mes_dashboard_view, mes_metric_list_view,
    mes_summary_api, mes_vin_suggest_api,
    mes_tracing_brands_api, mes_tracing_models_api,
    mes_metric_table_api, mes_metric_table_view,
    mes_metric_table_export,

    uud_report, uud_report_export,

    assembly_post_export_nophotos, assembly_post_export_custom,
)



urlpatterns = [
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),

    path('controller/', controller_dashboard, name='controller_dashboard'),
    path("api/remember-recent-post/", remember_recent_post, name="remember_recent_post"),

    path("master/", master_redirect, name="master_redirect"),
    path("master/dashboard/", master_dashboard, name="master_dashboard"),
    path("master/create-controller/", create_controller, name="create_controller"),
    path("master/reports/", defect_reports, name="defect_reports"),
    path("master/defects-table/", defect_table, name="defect_table"),
    path("master/api/get-defects/", get_defects, name="get_defects"),
    path("master/api/get-defect-stats/", get_defect_stats, name="get_defect_stats"),

    path('admin/', admin_dashboard, name='admin_dashboard'),

    path('profile/', profile, name='profile'),

    # Динамический маршрут для постов
    path('<int:post_id>/', post_detail, name='post_detail'),

    # Уведомления
    path("notifications/", notifications_view, name="notifications"),
    path("api/get-notifications/", get_notifications, name="get_notifications"),

    # Детали дефекта
    path("defect/<int:defect_id>/", sb_defect_details_view, name="sb_defect_details"),
    path("uud-notification/<str:vin_number>/", uud_defect_details_view, name="uud_defect_details"),

    # Данные справочника
    path('directory/', helpdesk_directory, name='helpdesk_directory'),


    path("master/controllers/", master_controller_panel, name="master_controller_panel"),
    path("master/controllers/<int:user_id>/change-password/", change_controller_password, name="change_controller_password"),
    path("master/controllers/<int:user_id>/delete/", delete_controller, name="delete_controller"),

    path('vin-tracking/', vin_tracking_select, name='vin_tracking_select'),
    path("vin-tracking/overview/", vin_tracking_overview, name="vin_tracking_overview"),

    path('vin-tracking/<str:vin>/', vin_tracking_view, name='vin_tracking_view'),
    path("vin-tracking/<str:vin>/download-excel/", export_vin_excel, name="export_vin_excel"),
    path('vin-tracking/<str:vin>/<str:post>/', vin_post_detail, name='vin_post_detail'),
    path("vin-tracking/post/<str:post>/", vin_tracking_post_vins, name="vin_tracking_post_vins"),


    path("master/incoming/", incoming_workshop_dashboard, name="incoming_workshop_dashboard"),
    path('incoming/reports/general/', incoming_general_report, name='incoming_general_report'),

    # Пост первичного осмотра
    path("incoming/body/report/", body_inspection_report, name="body_inspection_report"),
    path("incoming/body/table/", body_inspection_table, name="body_inspection_table"),
    path("incoming/body/export/", body_inspection_export, name="body_inspection_export"),
    path("incoming/body/form/", body_inspection_form, name="body_inspection_form"),

    # Пост комплектующих
    path("incoming/parts/report/", parts_acceptance_report, name="parts_acceptance_report"),
    path("incoming/parts/table/", parts_acceptance_table, name="parts_acceptance_table"),
    path("incoming/parts/export/", parts_acceptance_export, name="parts_acceptance_export"),
    path("incoming/parts/form/", parts_acceptance_form, name="parts_acceptance_form"),

    # Пост основной приемки
    path("incoming/final/report/", final_acceptance_report, name="final_acceptance_report"),
    path("incoming/final/table/", final_acceptance_table, name="final_acceptance_table"),
    path("incoming/final/export/", final_acceptance_export, name="final_acceptance_export"),
    path("incoming/final/form/", final_acceptance_form, name="final_acceptance_form"),

    # Пост приемки комплектующих
    path("incoming/containers/table/", containers_acceptance_table, name="containers_acceptance_table"),
    path("incoming/containers/export/", containers_acceptance_export, name="containers_acceptance_export"),

    path("master/assembly/", assembly_workshop_dashboard, name="assembly_workshop_dashboard"),

    path("assembly/current/report/", assembly_current_report, name="assembly_current_report"),
    path("assembly/current/table/", assembly_current_table, name="assembly_current_table"),
    path("assembly/current/export/", assembly_current_export, name="assembly_current_export"),

    path("assembly/table/", assembly_post_table, name="assembly_post_table"),

    path('assembly/export/', assembly_post_export, name='assembly_post_export'),
    path("assembly/export-nophotos/", assembly_post_export_nophotos, name="assembly_post_export_nophotos"),
    path("assembly/export-custom/", assembly_post_export_custom, name="assembly_post_export_custom"),

    path("manual_entry/", assembly_post_manual_entry, name="assembly_post_manual_entry"),
    path("report/", assembly_post_report, name="assembly_post_report"),
    path("edit/<str:vin>/<str:post_name>/<str:timestamp>/", assembly_post_edit, name="assembly_post_edit"),
    path("assembly/export/", assembly_post_export, name="assembly_post_export"),
    path("delete-entry/<str:vin>/<str:post>/<str:timestamp>/", delete_entry_view, name="delete_entry"),

    path("assembly/general-report/", assembly_general_report, name="assembly_general_report"),
    path("download-summary-report/", download_summary_report, name="download_summary_report"),

    # Изменение и удаление подсистем, узлов и дефектов
    path('manage-post-visibility/', manage_post_visibility, name='manage_post_visibility'),
    path("post/manage-post-visibility/update/zone/", assembly_zone_update, name="assembly_zone_update"),
    path("post/manage-post-visibility/delete/zone/", assembly_zone_delete, name="assembly_zone_delete"),

    path("post/manage-post-visibility/update/unit/", assembly_unit_update, name="assembly_unit_update"),
    path("post/manage-post-visibility/delete/unit/", assembly_unit_delete, name="assembly_unit_delete"),

    path("post/manage-post-visibility/update/defect/", assembly_defect_update, name="assembly_defect_update"),
    path("post/manage-post-visibility/delete/defect/", assembly_defect_delete, name="assembly_defect_delete"),

    # Поиск сотрудников и управление выборками
    path("employee-search/", employee_search, name="employee_search"),
    path("selection/edit/<int:selection_id>/", edit_selection, name="edit_selection"),
    path("selection/delete/<int:selection_id>/", delete_selection, name="delete_selection"),
    path("export/excel/", export_excel, name="export_excel"),
    path("export/history/", export_history, name="export_history"),
    path("export/history/load/<int:history_id>/", load_export_to_selection, name="load_export_to_selection"),
    path("export/history/re-export/<int:history_id>/", re_export_excel, name="re_export_excel"),
    path("export/history/edit/<int:history_id>/", edit_export_history, name="edit_export_history"),
    path("export/history/delete/<int:history_id>/", delete_export_history, name="delete_export_history"),
    path('delete_all_selections/', delete_all_selections, name='delete_all_selections'),

    # Делопроизводитель
    path("office/overview/", office_overview, name="office_overview"),
    path("office/export/", export_rvd_excel, name="export_rvd_excel"),
    path("office/delete-all/", delete_all_selections_dp, name="delete_all_selections_dp"),
    path("office/export-word/", export_word_rvd, name="export_word_rvd"),
    path("office/overtime-overview/", overtime_overview, name="office_overtime_overview"),
    path("office/assign-day-off/", assign_day_off, name="assign_day_off"),
    path('overtime/update_day_off/', update_day_off, name='update_day_off'),
    path('export/pending-day-off/', export_pending_day_off, name='export_pending_day_off'),

    # urls.py
    path("vin-list/<str:vin_type>/", vin_list_view, name="vin_list_view"),
    path("assembly/vins/<str:vin_type>/export/", export_vin_list_excel, name="export_vin_list_excel"),
    path("assembly/export/all_defects/", export_all_defects_excel, name="export_all_defects_excel"),

    path("in_development/", in_development, name="in_development"),


    # QRQC
    path("qrqc/", qrqc_dashboard_view, name="qrqc_dashboard"),
    path("qrqc/<str:brand>/", qrqc_brand_view, name="qrqc_dashboard_brand"),
    path("defect_details/", defect_details_view, name="defect_details"),

    # API KTV
    path("api/ktvdefect/list/", ktvdefect_list, name="ktvdefect_list"),
    # alias под шаблонный {% url "ktv_save" %}:
    path("api/ktvdefect/save/", ktvdefect_upsert, name="ktv_save"),
    # сохраним и «старый» апдейт-эндпоинт, если где-то используется
    path("api/ktvdefect/upsert/", ktvdefect_upsert, name="ktvdefect_upsert"),
    # удаление: поддержим и без id в URL, и с id в URL
    path("api/ktvdefect/delete/", ktvdefect_delete, name="ktv_delete"),
    path("api/ktvdefect/<int:pk>/delete/", ktvdefect_delete, name="ktv_delete_by_id"),


    #Counter

    path("counter/summary/", assembly_counter_dashboard, name="assembly_counter_dashboard"),
    path("api/counter/summary/", assembly_counter_api, name="assembly_counter_api"),

    # UUD 
    path('uud_controller/', uud_uniq, name='uud_uniq'),

    # MES

    # MES dashboard & generic
    path("mes/", mes_dashboard_view, name="mes_dashboard"),
    path("api/mes/summary/", mes_summary_api, name="mes_summary_api"),

    path("mes/dashboard", mes_dashboard_view, name="mes_dashboard_view"),
    path("mes/metric-list", mes_metric_list_view, name="mes_metric_list_view"),

    # MES: TRIM
    path("api/mes/trim/overview", trim_overview_api, name="trim_overview_api"),
    path("api/mes/trim/list", trim_list_api, name="trim_list_api"),

    # MES: BQA
    path("api/mes/bqa/overview", bqa_overview_api, name="bqa_overview_api"),
    path("api/mes/bqa/list", bqa_list_api, name="bqa_list_api"),

    # MES: QA
    path("api/mes/qa/overview", qa_overview_api, name="qa_overview_api"),
    path("api/mes/qa/list", qa_list_api, name="qa_list_api"),

    # MES: UUD
    path("api/mes/uud/overview", uud_overview_api, name="uud_overview_api"),
    path("api/mes/uud/list", uud_list_api, name="uud_list_api"),

    # MES: VES
    path("api/mes/ves/overview", ves_overview_api, name="ves_overview_api"),
    path("api/mes/ves/list", ves_list_api, name="ves_list_api"),

    path("api/mes/tracing/brands", mes_tracing_brands_api, name="mes_tracing_brands_api"),
    path("api/mes/tracing/models", mes_tracing_models_api, name="mes_tracing_models_api"),
    path("api/mes/history/vins", mes_vin_suggest_api, name="mes_vin_suggest_api"),

    # HTML-страница с динамической таблицей
    path("mes/table", mes_metric_table_view, name="mes_metric_table_view"),

    # API для динамической таблицы
    path("api/mes/table", mes_metric_table_api, name="mes_metric_table_api"),

    path("api/mes/table/export", mes_metric_table_export, name="mes_metric_table_export"),

    #UUD
    path("uud_report", uud_report, name="uud_report"),
    path("uud-report/export/", uud_report_export, name="uud_report_export"),

]
