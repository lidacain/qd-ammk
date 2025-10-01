import os
import django
import pandas as pd

# Django env
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "factory_server.settings")
django.setup()

from django.utils.timezone import now  # если где-то пригодится
from supplies.models import TraceData

EXCEL_FILE_PATH = "трейсинг.xlsx"  # путь к файлу

def to_int_or_none(value):
    """Пытается привести к int, иначе возвращает None (для хранения NULL в БД)."""
    s = str(value).strip()
    if s == "":
        return None
    try:
        return int(s)
    except Exception:
        return None

def load_trace_data():
    """Загрузка/обновление данных из Excel в БД по VIN RK (upsert)."""
    try:
        df = pd.read_excel(EXCEL_FILE_PATH, dtype=str, engine="openpyxl")
        df.fillna("", inplace=True)

        for _, row in df.iterrows():
            # Пропускаем строки без корректного порядкового номера в первом столбце
            first_cell = str(row.iloc[0]).strip()
            if not first_cell.isdigit():
                continue

            vin_rk = str(row.iloc[5]).strip()
            if not vin_rk:
                continue

            # ── Маппинг столбцов (0-based индексы):
            # A:0 (порядковый)
            brand               = str(row.iloc[1]).strip()   # B
            model               = str(row.iloc[2]).strip()   # C
            config_code         = str(row.iloc[3]).strip()   # D
            body_number         = str(row.iloc[4]).strip()   # E
            # F: vin_rk = iloc[5]
            engine_number       = str(row.iloc[6]).strip()   # G
            color_1c            = str(row.iloc[7]).strip()   # H
            body_color          = str(row.iloc[8]).strip()   # I
            interior_color      = str(row.iloc[9]).strip()   # J (NEW ранее)
            body_type           = str(row.iloc[10]).strip()  # K
            seat_capacity       = to_int_or_none(row.iloc[11])  # L
            engine_power        = str(row.iloc[12]).strip()  # M
            engine_volume       = to_int_or_none(row.iloc[13])  # N
            weight              = to_int_or_none(row.iloc[14])  # O
            gross_weight        = to_int_or_none(row.iloc[15])  # P

            # ── НОВОЕ: Q, R вставлены перед прежним production_year
            tdmm_front_axle     = to_int_or_none(row.iloc[16])  # Q: ТДММ передняя ось
            tdmm_rear_axle      = to_int_or_none(row.iloc[17])  # R: ТДММ задняя ось

            # ── Всё, что было после, сдвинулось на +2:
            production_year     = to_int_or_none(row.iloc[18])  # было 16 → стало 18 (S)
            modification        = str(row.iloc[19]).strip()     # было 17 → 19 (T)
            transmission        = str(row.iloc[20]).strip()     # было 18 → 20 (U)

            # Пропускаемые/пустые колонки между 21..26 (если есть)
            butch_number        = str(row.iloc[27]).strip()
            vin_c               = str(row.iloc[28]).strip()

            # Upsert по vin_rk
            TraceData.objects.update_or_create(
                vin_rk=vin_rk,
                defaults={
                    "brand": brand or "Unknown",
                    "model": model or "Unknown",
                    "config_code": config_code,
                    "body_number": body_number,
                    "engine_number": engine_number,
                    "engine_volume": engine_volume,
                    "modification": modification,
                    "body_color": body_color,
                    "transmission": transmission,
                    "engine_power": engine_power,
                    "gross_weight": gross_weight,
                    "weight": weight,
                    "config_code_extra": "",  # если появится столбец — подхватим позже
                    "color_1c": color_1c,
                    "body_type": body_type,
                    "seat_capacity": seat_capacity,
                    "production_year": production_year,
                    "vin_c": vin_c,
                    "interior_color": interior_color,
                    "tdmm_front_axle": tdmm_front_axle,
                    "tdmm_rear_axle": tdmm_rear_axle,
                    "butch_number": butch_number,
                    # "date_added" НЕ трогаем: при создании установится по default=now
                }
            )
            print(f"✔ VIN RK {vin_rk}: добавлен/обновлён.")

        print("✅ Загрузка завершена.")
    except Exception as e:
        print(f"❌ Ошибка при загрузке данных: {e}")

if __name__ == "__main__":
    load_trace_data()
