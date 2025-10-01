from django.core.management.base import BaseCommand
from vehicle_history.models import VINHistory


class Command(BaseCommand):
    help = "Переименовывает пост 'Экстерьер и интерьер' в 'Экстерьер' во всех VINHistory"

    def handle(self, *args, **kwargs):
        updated = 0

        for vin_obj in VINHistory.objects.all():
            history = vin_obj.history
            modified = False

            for zone in list(history.keys()):
                if "ТЕСТ Трек" in history[zone]:
                    history[zone]["Тест трек"] = history[zone].pop("ТЕСТ ТРЕК")
                    modified = True

            if modified:
                vin_obj.history = history
                vin_obj.save()
                updated += 1
                self.stdout.write(self.style.SUCCESS(f"Обновлён VIN: {vin_obj.vin}"))

        self.stdout.write(self.style.SUCCESS(f"Готово. Обновлено {updated} VINов."))