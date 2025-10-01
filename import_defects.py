import pandas as pd
from assembly.models import AssemblyDefect

def import_defects_from_excel(filepath):
    df = pd.read_excel(filepath)

    # Удаляем лишние пробелы и пропуски
    df = df[['NameD', 'NameDE']].dropna()
    df['NameD'] = df['NameD'].astype(str).str.strip()
    df['NameDE'] = df['NameDE'].astype(str).str.strip()

    count_created = 0
    for _, row in df.iterrows():
        name_ru = row['NameD']
        name_en = row['NameDE']

        obj, created = AssemblyDefect.objects.get_or_create(
            name=name_ru,
            defaults={"nameENG": name_en}
        )
        if not created:
            # Обновим англ. перевод, если он пустой
            if not obj.nameENG:
                obj.nameENG = name_en
                obj.save()

        print(f"{'✅' if created else '⚠️'} {name_ru} / {name_en}")
        count_created += int(created)

    print(f"\nИтог: добавлено {count_created} новых дефектов из {len(df)}")

# Пример запуска:
# import_defects_from_excel('путь_к_файлу/defects.xlsx')