import pandas as pd
from assembly.models import AssemblyUnit

# Путь к файлу
file_path = "Детали_с_зонами_финал.xlsx"

# Загрузка данных
df = pd.read_excel(file_path)

# Счётчики
created_count = 0
updated_count = 0

for _, row in df.iterrows():
    name = str(row['Деталь']).strip()
    zone = str(row['Зона']).strip()

    unit, created = AssemblyUnit.objects.update_or_create(
        name=name,
        defaults={'zone': zone}
    )
    if created:
        created_count += 1
    else:
        updated_count += 1

print(f"✅ Импорт завершен: создано — {created_count}, обновлено — {updated_count}")