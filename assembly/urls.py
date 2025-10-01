from django.urls import path
from .views import (
    vin_lookup,
    view_image,
    torque_control_dkd,
    get_assembly_parts,
    get_part_details,
    vin_defects_api,
    uud_dkd,
    torque_graph_view,
    offline_defects_api,
    uud_check_dkd,
    uud_zone_data_api,
    search_vin,
    assembly_post_view,
    assembly_vin_scan_view,
    assembly_vin_trimout_view,
    ves_views,
    ves_pass_view,
    uud_uniq,
    us_to_uud,
    uud_to_us,
    uud_to_uudzone,
    uudzone_to_uud,
    uud_current_state,
    uud_defect_info,
    uud_defect_decide,
    uud_defect_submit_fix,
    uud_defect_mark_impossible,
    documentation_views,
    documentation_table_view,
    export_documentation_extended,
    vin_status_api,
    marriage_view,
    marriage_table_view,
    marriage_table_export,
)
app_name = 'assembly'

urlpatterns = [
    path("view-image/<path:image_path>/", view_image, name="view_image"),
    path("torque_control_dkd/", torque_control_dkd, name="torque_control_dkd"),
    path("uud_dkd/", uud_dkd, name="uud_dkd"),
    path("uud_check_dkd/", uud_check_dkd, name="uud_check_dkd"),

    path('torque_graph_dkd/', torque_graph_view, name='torque_graph'),

    # API-эндпоинты
    path("api/assembly-parts/", get_assembly_parts, name="get_assembly_parts"),
    path("api/part-details/", get_part_details, name="get_part_details"),
    path("api/vin_defects/", vin_defects_api, name="vin_defects_api"),
    path("api/vin-lookup/", vin_lookup, name="vin_lookup"),
    path('api/get-offline-defects/', offline_defects_api, name='get_offline_defects'),
    path("api/uud-zone-data/", uud_zone_data_api, name="uud_zone_data_api"),


    path("api/search_vin/", search_vin, name="search_vin"),

    # Torque_control for different line
    path('torque_control_chery/', lambda r: assembly_post_view(r, line="chery", post_suffix="line Chery"),
         name='torque_control_chery'),
    path('torque_control_gwm/', lambda r: assembly_post_view(r, line="gwm", post_suffix="line GWM"),
         name='torque_control_gwm'),
    path('torque_control_changan/', lambda r: assembly_post_view(r, line="changan", post_suffix="line Changan"),
         name='torque_control_changan'),
    path('torque_control_frame/', lambda r: assembly_post_view(r, line="frame", post_suffix="line Frame"),
         name='torque_control_frame'),
    path('torque_control_sub_changan/', lambda r: assembly_post_view(r, line="sub changan", post_suffix="line Sub Changan"),
         name='torque_control_sub_changan'),
    path('torque_control_sub_chery/', lambda r: assembly_post_view(r, line="sub chery", post_suffix="line Sub Chery"),
         name='torque_control_sub_chery'),
    path('torque_control_sub_gwm/', lambda r: assembly_post_view(r, line="sub gwm", post_suffix="line Sub GWM"),
         name='torque_control_sub_gwm'),


    # Chassis for different line
    path('chassis_chery/', lambda r: assembly_post_view(r, line="chery", post_suffix="line Chery"),
            name='chassis_chery'),
    path('chassis_gwm/', lambda r: assembly_post_view(r, line="gwm", post_suffix="line GWM"),
            name='chassis_gwm'),
    path('chassis_changan/', lambda r: assembly_post_view(r, line="changan", post_suffix="line Changan"),
            name='chassis_changan'),
    path('chassis_frame/', lambda r: assembly_post_view(r, line="frame", post_suffix="line Frame"),
         name='chassis_frame'),
    path('chassis_sub_changan/', lambda r: assembly_post_view(r, line="sub changan", post_suffix="line Sub Changan"),
         name='chassis_sub_changan'),
    path('chassis_sub_chery/', lambda r: assembly_post_view(r, line="sub chery", post_suffix="line Sub Chery"),
         name='chassis_sub_chery'),
    path('chassis_sub_gwm/', lambda r: assembly_post_view(r, line="sub gwm", post_suffix="line Sub GWM"),
         name='chassis_sub_gwm'),


    # Final current control for different line
    path('final_current_control_chery/', lambda r: assembly_post_view(r, line="chery", post_suffix="line Chery"),
            name='final_current_control_chery'),
    path('final_current_control_gwm/', lambda r: assembly_post_view(r, line="gwm", post_suffix="line GWM"),
            name='final_current_control_gwm'),
    path('final_current_control_changan/', lambda r: assembly_post_view(r, line="changan", post_suffix="line Changan"),
            name='final_current_control_changan'),
    path('final_current_control_frame/', lambda r: assembly_post_view(r, line="frame", post_suffix="line Frame"),
         name='final_current_control_frame'),
    path('final_current_control_sub_changan/', lambda r: assembly_post_view(r, line="sub changan", post_suffix="line Sub Changan"),
         name='final_current_control_sub_changan'),
    path('final_current_control_sub_chery/',
         lambda r: assembly_post_view(r, line="sub chery", post_suffix="line Sub Chery"),
         name='final_current_control_sub_chery'),
    path('final_current_control_sub_gwm/',
         lambda r: assembly_post_view(r, line="sub gwm", post_suffix="line Sub GWM"),
         name='final_current_control_sub_gwm'),

    # Gaps and Drops for one line
    path('gaps_and_drops/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
            name='gaps_and_drops'),

    # Exterior and interior for one line
    path('exterior/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
            name='exterior'),

    path('interior/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
         name='interior'),

    # Trunk for one line
    path('trunk/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
         name='trunk'),

    # The motor for one line
    path('the_motor/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
         name='the_motor'),

    # Functional for one line
    path('functional/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
         name='functional'),

    # Geometry of wheels for one line
    path('geometry_of_wheels/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
         name='geometry_of_wheels'),

    # Adjusting the headlights and calibrating the steering wheel for one line
    path('adjusting_the_headlights_and_calibrating_the_steering_wheel/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
         name='adjusting_the_headlights_and_calibrating_the_steering_wheel'),

    # Breaking system for one line
    path('breaking_system/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
         name='breaking_system'),

    # Underbody for one line
    path('underbody/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
         name='underbody'),

    # ADAS for different line
    path('adas_chery/', lambda r: assembly_post_view(r, line="chery", post_suffix="line Chery"),
         name='adas_chery'),
    path('adas_gwm/', lambda r: assembly_post_view(r, line="gwm", post_suffix="line GWM"),
         name='adas_gwm'),
    path('adas_changan/', lambda r: assembly_post_view(r, line="changan", post_suffix="line Changan"),
         name='adas_changan'),

    # AVM for different line
    path('avm_chery/', lambda r: assembly_post_view(r, line="chery", post_suffix="line Chery"),
         name='avm_chery'),
    path('avm_gwm/', lambda r: assembly_post_view(r, line="gwm", post_suffix="line GWM"),
         name='avm_gwm'),
    path('avm_changan/', lambda r: assembly_post_view(r, line="changan", post_suffix="line Changan"),
         name='avm_changan'),

    # Tightness of the body for one line
    path('tightness_of_the_body/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
         name='tightness_of_the_body'),

    # Test track for one line
    path('diagnostics/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
         name='diagnostics'),

    # Test track for one line
    path('test_track/', lambda r: assembly_post_view(r, line="1", post_suffix=""),
         name='test_track'),

    # Final for one line
    path('documentation/', lambda r: documentation_views(r, line="1", post_suffix=""),
         name='documentation'),

    path('counter_chery/', lambda r: assembly_vin_scan_view(r, line="chery"), name='counter_chery'),
    path('counter_gwm/', lambda r: assembly_vin_scan_view(r, line="gwm"), name='counter_gwm'),
    path('counter_frame/', lambda r: assembly_vin_scan_view(r, line="frame"), name='counter_frame'),
    path('counter_changan/', lambda r: assembly_vin_scan_view(r, line="changan"), name='counter_changan'),

    path('counter_trim_out_chery/', lambda r: assembly_vin_trimout_view(r, line="chery"),
         name='counter_trim_out_chery'),
    path('counter_trim_out_gwm/', lambda r: assembly_vin_trimout_view(r, line="gwm"), name='counter_trim_out_gwm'),
    path('counter_trim_out_frame/', lambda r: assembly_vin_trimout_view(r, line="frame"),
         name='counter_trim_out_frame'),
    path('counter_trim_out_changan/', lambda r: assembly_vin_trimout_view(r, line="changan"),
         name='counter_trim_out_changan'),




    #VES

    path("ves/", ves_views, {"line": "1"}, name="ves"),

    path('ves_pass_log/', ves_pass_view, name='ves_pass_view'),

    path("uud/", uud_uniq, name="uud_uniq"),
    path("uud/state/", uud_current_state, name="uud_current_state"),
    path("uud/us-to-uud/", us_to_uud, name="us_to_uud"),
    path("uud/uud-to-zone/", uud_to_uudzone, name="uud_to_uudzone"),
    path("uud/zone-to-uud/", uudzone_to_uud, name="uudzone_to_uud"),
    path("uud/uud-to-us/", uud_to_us, name="uud_to_us"),

    path("api/uud/defect/submit-fix/", uud_defect_submit_fix, name="uud_defect_submit_fix"),
    path("api/uud/defect/decide/", uud_defect_decide, name="uud_defect_decide"),
    path("api/uud/defect/info/", uud_defect_info, name="uud_defect_info"),
    path("uud/defect/mark-impossible", uud_defect_mark_impossible, name="uud_defect_mark_impossible"),

    path("documentation_table/", documentation_table_view, name="documentation_table"),
    path("docs/export/extended/", export_documentation_extended, name="docs_export_extended"),

    path("api/vin-status/", vin_status_api, name="vin_status_api"),

    path("marriage/", marriage_view, name="assembly_marriage"),
    path("marriage/table/", marriage_table_view, name="assembly_marriage_table"),
    path("marriage/export/", marriage_table_export, name="assembly_marriage_export"),


]
