from django.urls import path
from .views import (
    container_unloading_zone_2,
    view_image,
    container_unloading_zone_sb,
    component_unloading_zone_dkd,
    search_engine_number,
    body_unloading_zone_dkd,
    search_vin,
    main_unloading_zone_dkd,
    vin_defects_api,
    get_body_details_by_zone,
    container_inspection_dkd,
    search_container,
    trash
)


urlpatterns = [
    path("view-image/<path:image_path>/", view_image, name="view_image"),


    path("container_unloading_zone_2/", container_unloading_zone_2, name="container_unloading_zone_2"),


    path("container_unloading_zone_sb/", container_unloading_zone_sb, name="container_unloading_zone_sb"),


    path("dvs_unloading_zone_dkd/", component_unloading_zone_dkd, name="component_unloading_zone_dkd"),
    path("body_unloading_zone_dkd/", body_unloading_zone_dkd, name="body_unloading_zone_dkd"),
    path("main_unloading_zone_dkd/", main_unloading_zone_dkd, name="main_unloading_zone_dkd"),

    path("api/search_engine/", search_engine_number, name="search_engine"),
    path("api/search_vin/", search_vin, name="search_vin"),
    path("api/vin_defects/", vin_defects_api, name="vin_defects_api"),
    path("api/body-details/", get_body_details_by_zone, name="get_body_details_by_zone"),
    path("api/search_container/", search_container, name="search_container"),

    path("container_inspection_dkd/", container_inspection_dkd, name="container_inspection_dkd"),
    path("trash/", trash, name="trash"),
]
