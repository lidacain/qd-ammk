from django.apps import AppConfig

class VehicleHistoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "vehicle_history"

    def ready(self):
        from . import signals  # noqa: F401
