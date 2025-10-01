# vehicle_history/management/commands/export_trace_vins.py
from django.core.management.base import BaseCommand
from django.db.models import Q
import os
import sys

# pandas используется для чтения/записи Excel — проект обычно имеет pandas, если нет, поставьте: pip install pandas openpyxl
import pandas as pd

# Попытки импортов модели TraceData (в вашем проекте она встречалась в нескольких местах)
_TRACE_IMPORTS = [
    "trace_data.models",
    "vehicle_history.models",
    "vehicle_history.trace_models",
    "trace.models",
]


def import_tracedata_model():
    for mod in _TRACE_IMPORTS:
        try:
            module = __import__(mod, fromlist=["TraceData"])
            if hasattr(module, "TraceData"):
                return module.TraceData
        except Exception:
            continue
    # Если не найдено — попробуем найти класс по имени в установленных приложениях (последняя попытка)
    for app in sys.modules.values():
        try:
            if hasattr(app, "TraceData"):
                return getattr(app, "TraceData")
        except Exception:
            continue
    raise ImportError(
        "Не удалось импортировать модель TraceData. Убедитесь, что она доступна в одном из модулей: "
        + ", ".join(_TRACE_IMPORTS)
    )


class Command(BaseCommand):
    help = "Export TraceData info for VINs listed in an Excel file (sheet name default: vin_ch)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            "-i",
            dest="input",
            required=False,
            help="Path to input Excel file with VINs (default: vin_ch.xlsx)",
        )
        parser.add_argument(
            "--sheet",
            "-s",
            dest="sheet",
            required=False,
            help="Sheet name that contains VIN list (default: 'vin_ch' or first sheet)",
        )
        parser.add_argument(
            "--output",
            "-o",
            dest="output",
            required=False,
            help="Path to output Excel file (default: trace_vins_output.xlsx)",
        )
        parser.add_argument(
            "--vin-column",
            dest="vin_column",
            required=False,
            default="vin",
            help="Column name in input sheet that contains VINs (default: vin). If numeric index is needed - specify column name exactly.",
        )

    def handle(self, *args, **options):
        input_path = options.get("input") or "vin_ch.xlsx"
        sheet_name = options.get("sheet")
        output_path = options.get("output") or "trace_vins_output.xlsx"
        vin_col = options.get("vin_column") or "vin"

        if not os.path.exists(input_path):
            self.stderr.write(self.style.ERROR(f"Input file not found: {input_path}"))
            return

        # читаем Excel
        self.stdout.write(f"Читаем VIN-ы из {input_path} (лист: {sheet_name or 'по умолчанию'}) ...")
        try:
            if sheet_name:
                df_in = pd.read_excel(input_path, sheet_name=sheet_name, engine="openpyxl")
            else:
                # пробуем лист 'vin_ch', иначе первый лист
                try:
                    df_in = pd.read_excel(input_path, sheet_name="vin_ch", engine="openpyxl")
                except Exception:
                    df_in = pd.read_excel(input_path, sheet_name=0, engine="openpyxl")
        except Exception as e:
            self.stderr.write(self.style.ERROR("Ошибка при чтении Excel: " + str(e)))
            return

        if vin_col not in df_in.columns:
            # Попытка нормализовать: строчные/верхние, пробелы
            cols_lower = {c.lower(): c for c in df_in.columns}
            if vin_col.lower() in cols_lower:
                vin_col = cols_lower[vin_col.lower()]
            else:
                # попытка найти первую колонку содержащую 'vin'
                vin_candidates = [c for c in df_in.columns if "vin" in c.lower()]
                if vin_candidates:
                    vin_col = vin_candidates[0]
                else:
                    self.stderr.write(self.style.ERROR(f"Не найдена колонка VIN (ищем '{options.get('vin_column')}'). Доступные колонки: {list(df_in.columns)}"))
                    return

        vin_series = df_in[vin_col].dropna().astype(str).str.strip().str.upper().unique().tolist()
        if not vin_series:
            self.stderr.write(self.style.ERROR("Не найдено VIN-ов в входном файле."))
            return

        self.stdout.write(f"Найдено VIN-ов: {len(vin_series)} (пример: {vin_series[:5]})")

        # импорт модели
        try:
            TraceData = import_tracedata_model()
        except ImportError as e:
            self.stderr.write(self.style.ERROR(str(e)))
            return

        # Определяем реальные (concrete) поля модели и VIN-поля
        all_fields = [f for f in TraceData._meta.get_fields() if getattr(f, "concrete", False) and not getattr(f, "many_to_many", False) and not getattr(f, "one_to_many", False)]
        field_names = {f.name for f in all_fields}
        vin_candidates = [name for name in ("vin_rk", "vin_c", "vin") if name in field_names]
        if not vin_candidates:
            self.stderr.write(self.style.ERROR(
                f"В модели TraceData нет полей vin_rk/vin_c/vin. Доступные поля: {sorted(field_names)}"
            ))
            return

        # Фильтруем по всем найденным VIN-полям (OR)
        q = Q()
        for vf in vin_candidates:
            q |= Q(**{f"{vf}__in": vin_series})
        qs = TraceData.objects.filter(q)
        self.stdout.write(f"В TraceData найдено записей: {qs.count()} (по полям {vin_candidates})")

        def _serialize(v):
            from datetime import datetime, date
            if isinstance(v, (datetime, date)):
                return v.isoformat(sep=" ")
            return v if v is not None else ""

        rows = []
        # Сформируем порядок колонок: сначала VIN-поля, затем остальные
        ordered_cols = [c for c in ("vin_rk", "vin_c", "vin") if c in field_names]
        other_cols = [f.name for f in all_fields if f.name not in ordered_cols]
        export_cols = ordered_cols + other_cols

        matched_vins = set()
        vins_set = set(vin_series)

        for idx, obj in enumerate(qs.iterator(), 1):
            row = {}
            for col in export_cols:
                row[col] = _serialize(getattr(obj, col, ""))

            # зафиксируем, по какому полю совпал VIN
            matched_field = ""
            for vf in ordered_cols:
                val = getattr(obj, vf, None)
                if isinstance(val, str) and val.upper() in vins_set:
                    matched_field = vf
                    matched_vins.add(val.upper())
                    break
            row["_matched_vin_field"] = matched_field
            row["_pk"] = getattr(obj, "pk", "")
            rows.append(row)
            if idx % 200 == 0:
                self.stdout.write(f"...обработано {idx} записей")

        # Добавим отсутствующие VIN как пустые строки для удобной сверки
        missing_vins = [v for v in vin_series if v not in matched_vins]
        for mv in missing_vins:
            empty = {c: "" for c in export_cols}
            if ordered_cols:
                empty[ordered_cols[0]] = mv
            empty["_matched_vin_field"] = ""
            empty["_pk"] = ""
            rows.append(empty)

        # Сохраняем в Excel через pandas
        df_out = pd.DataFrame(rows)
        # ставим VIN-поля впереди, затем остальные, плюс служебные
        front = [c for c in ("vin_rk", "vin_c", "vin") if c in df_out.columns]
        tail = [c for c in df_out.columns if c not in front]
        df_out = df_out.loc[:, front + [c for c in tail if c not in ("_matched_vin_field", "_pk")] + ["_matched_vin_field", "_pk"]]

        try:
            df_out.to_excel(output_path, index=False, engine="openpyxl")
            self.stdout.write(self.style.SUCCESS(f"Экспорт завершён: {output_path} (строк: {len(df_out)})"))
        except Exception as e:
            self.stderr.write(self.style.ERROR("Ошибка при сохранении Excel: " + str(e)))
            return