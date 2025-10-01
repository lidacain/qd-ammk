import pandas as pd
from assembly.models import AssemblyUnit

def import_units_from_excel(filepath):
    df = pd.read_excel(filepath)

    # Очистим и нормализуем названия
    names = df.iloc[:, 0].dropna().apply(lambda x: str(x).strip())

    count_created = 0
    for name in names:
        obj, created = AssemblyUnit.objects.get_or_create(name=name)
        if created:
            count_created += 1
            print(f"✅ Добавлено: {name}")
        else:
            print(f"⚠️ Уже существует: {name}")

    print(f"\nИтог: добавлено {count_created} новых узлов из {len(names)}")

# Запуск
import_units_from_excel('Книга1 (1).xlsx')
