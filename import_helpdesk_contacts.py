import os
import django
import pandas as pd

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "factory_server.settings")
django.setup()

from users.models import HelpdeskContact

def import_helpdesk_contacts(file_path):
    df = pd.read_excel(file_path)

    # Удаляем пробелы в названиях столбцов
    df.columns = df.columns.str.strip()

    created_count = 0

    for _, row in df.iterrows():
        if pd.isna(row["Сотрудник"]):
            continue

        HelpdeskContact.objects.create(
            position=row["Должность"],
            employee_name=row["Сотрудник"],
            phone_number=str(row["мобильный"]),
            email=row["E-mail"],
            department=row["Отдел"]
        )
        created_count += 1

    print(f"✅ Импорт завершен. Добавлено {created_count} записей.")

if __name__ == "__main__":
    import_helpdesk_contacts("справочник от 18.08.2025.xlsx")