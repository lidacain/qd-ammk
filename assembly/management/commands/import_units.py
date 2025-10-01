from django.core.management.base import BaseCommand
from assembly.models import AssemblyUnit
import pandas as pd
import os

class Command(BaseCommand):
    help = "Импорт узлов из Excel в модель AssemblyUnit"

    def handle(self, *args, **kwargs):
        file_path = "Детали_с_зонами_финал.xlsx"
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"Файл '{file_path}' не найден"))
            return

        df = pd.read_excel(file_path)

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

        self.stdout.write(self.style.SUCCESS(
            f"✅ Импорт завершен: создано — {created_count}, обновлено — {updated_count}"
        ))