import os
from pathlib import Path
import pandas as pd
from django.core.management.base import BaseCommand
from django.conf import settings
from vehicle_history.models import VINHistory

SIGNOFF_POST_CANDIDATES = {s.lower() for s in [
    "Документация", "Documentation", "Docs", "Документы"
]}

def _has_signoff(history: dict) -> bool:
    if not isinstance(history, dict):
        return False
    for _, posts in (history or {}).items():
        if not isinstance(posts, dict):
            continue
        for post_name, entries in (posts or {}).items():
            if str(post_name).strip().lower() in SIGNOFF_POST_CANDIDATES:
                return bool(entries) and isinstance(entries, list)
    return False


class Command(BaseCommand):
    help = "Проверяет VIN из Excel на прохождение Sign Off (пост 'Документация')."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, default="vins.xlsx",
                            help="Путь к Excel (по умолчанию рядом с manage.py), VIN в первом столбце.")
        parser.add_argument("--sheet", type=str, default=None,
                            help="Имя листа. Если не задано — берётся первый лист.")
        parser.add_argument("--print-ok", action="store_true",
                            help="Также выводить VIN, которые прошли Sign Off.")

    def handle(self, *args, **options):
        base_dir = Path(getattr(settings, "BASE_DIR", Path.cwd()))
        file_path = Path(options["file"])
        if not file_path.is_absolute():
            file_path = base_dir / file_path
        if not file_path.exists():
            self.stderr.write(self.style.ERROR(f"Файл не найден: {file_path}"))
            return

        sheet = options["sheet"]
        # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: всегда получаем DataFrame, а не dict
        try:
            df = pd.read_excel(
                file_path,
                dtype=str,
                engine="openpyxl",
                sheet_name=(sheet if sheet is not None else 0)  # ← только один лист
            )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Не удалось прочитать Excel: {e}"))
            return

        if df is None or df.shape[1] == 0:
            self.stderr.write(self.style.ERROR("В Excel нет данных."))
            return

        vins = (
            df.iloc[:, 0]
            .dropna()
            .astype(str)
            .str.strip()
            .str.upper()
            .tolist()
        )
        vins = [v for v in vins if v]
        vins_unique = sorted(set(vins))
        if not vins_unique:
            self.stdout.write(self.style.WARNING("В Excel не найдено VIN-номеров."))
            return

        qs = VINHistory.objects.filter(vin__in=vins_unique).values_list("vin", "history")
        history_by_vin = {vin.upper(): history for vin, history in qs}

        missing, ok = [], []
        for vin in vins_unique:
            h = history_by_vin.get(vin)
            (ok if (h and _has_signoff(h)) else missing).append(vin)

        self.stdout.write(self.style.NOTICE(f"Всего VIN в файле: {len(vins_unique)}"))
        self.stdout.write(self.style.SUCCESS(f"Прошли Sign Off: {len(ok)}"))
        self.stdout.write(self.style.WARNING(f"НЕ прошли Sign Off: {len(missing)}"))

        if missing:
            self.stdout.write(self.style.WARNING("\nVIN без Sign Off:"))
            for v in missing:
                self.stdout.write(v)

        if options["print_ok"] and ok:
            self.stdout.write(self.style.SUCCESS("\nVIN с Sign Off:"))
            for v in ok:
                self.stdout.write(v)
