import os
import sys
import django
import pandas as pd

# Если запускаешь не из корня проекта, раскомментируй и поправь путь:
# sys.path.append("/Users/adil/PycharmProjects/amm_server/factory_server")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "factory_server.settings")
django.setup()

from users.models import Employee

# --- 1) Загружаем Excel
df = pd.read_excel("11212.xlsx")

# --- 2) Чистим заголовки: обрезаем пробелы и приводим к нижнему регистру
df.columns = [str(c).strip().lower() for c in df.columns]

# Теперь ожидаем: 'name', 'position', 'department' (без хвостовых пробелов)

# --- 3) Хелпер для строковых полей
def clean_cell(x):
    if pd.isna(x):
        return None
    s = str(x).strip()
    if s in {"", "-", "—"}:
        return None
    return s

created, updated = 0, 0

# --- 4) Проходим по строкам
required_cols = {"name", "position"}  # без них не создаём запись
missing = required_cols - set(df.columns)
if missing:
    raise ValueError(f"В Excel не хватает колонок: {', '.join(sorted(missing))}")

for _, row in df.iterrows():
    name = clean_cell(row.get("name"))
    position = clean_cell(row.get("position"))
    department = clean_cell(row.get("department"))  # будет None если '-' или пусто

    # Пропускаем пустые имена/должности
    if not name or not position:
        continue

    employee, is_created = Employee.objects.update_or_create(
        name=name,
        defaults={
            "position": position,
            "department": department,
        }
    )
    if is_created:
        created += 1
    else:
        updated += 1

print(f"✅ Загружено: {created} новых, {updated} обновлено.")
