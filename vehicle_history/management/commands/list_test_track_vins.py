# vehicle_history/management/commands/list_test_track_vins.py
from django.core.management.base import BaseCommand
from vehicle_history.models import VINHistory
import csv

def _contains_post(obj, target_key: str) -> bool:
    """
    Рекурсивный поиск ключа поста в произвольной структуре history (dict/list).
    Совпадение по имени ключа (без регистра и лишних пробелов).
    """
    norm = target_key.strip().lower()

    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.strip().lower() == norm:
                return True
            if _contains_post(v, target_key):
                return True
        return False

    if isinstance(obj, list):
        for item in obj:
            if _contains_post(item, target_key):
                return True
        return False

    return False


class Command(BaseCommand):
    help = "Выводит уникальные VIN-номера, проходившие заданный пост (по умолчанию: 'Тест трек')."

    def add_arguments(self, parser):
        parser.add_argument(
            "--post",
            default="Тест трек",
            help="Название поста для поиска (по умолчанию: 'Тест трек').",
        )
        parser.add_argument(
            "--csv",
            dest="csv_path",
            help="Путь к CSV-файлу для сохранения VIN (необязательно).",
        )

    def handle(self, *args, **options):
        target_post = options["post"]
        csv_path = options.get("csv_path")

        vins = set()

        # Берём только нужные поля, чтобы не тянуть лишнее
        qs = VINHistory.objects.only("vin", "history")

        for vh in qs.iterator():
            history = getattr(vh, "history", {}) or {}
            try:
                if _contains_post(history, target_post):
                    vin = getattr(vh, "vin", None)
                    if vin:
                        vins.add(vin)
            except Exception as e:
                self.stderr.write(self.style.WARNING(f"⚠️ Пропуск VIN {getattr(vh, 'vin', '—')}: {e}"))

        vins_sorted = sorted(vins)

        # Вывод в консоль
        self.stdout.write(self.style.SUCCESS(f"Найдено VIN: {len(vins_sorted)}"))
        for vin in vins_sorted:
            self.stdout.write(vin)

        # Опционально — сохранить в CSV
        if csv_path:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["VIN"])
                for vin in vins_sorted:
                    writer.writerow([vin])
            self.stdout.write(self.style.SUCCESS(f"CSV сохранён: {csv_path}"))