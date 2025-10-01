import pandas as pd
from django.core.management.base import BaseCommand
from supplies.models import Defect, Post


class Command(BaseCommand):
    help = "Импорт дефектов из Excel в базу данных"

    def handle(self, *args, **kwargs):
        file_path = "/Users/adil/PycharmProjects/amm_server/factory_server/supplies/management/commands/defects.xlsx"  # Укажите путь к файлу
        xls = pd.ExcelFile(file_path)
        df = pd.read_excel(xls, sheet_name="Лист1")

        # Объединяем русское и английское название
        df["combined_name"] = df["NameD"].astype(str) + " / " + df["NameDE"].astype(str)

        # Получаем первые четыре поста
        posts = list(Post.objects.all()[:4])

        # Добавляем дефекты в базу данных и привязываем их к первым четырем постам
        for name in df["combined_name"].dropna().unique():
            defect, created = Defect.objects.get_or_create(name=name)
            if created:
                defect.posts.set(posts)  # Привязываем к первым четырем постам
                self.stdout.write(self.style.SUCCESS(f'Добавлен дефект: {name} и привязан к первым четырем постам'))
            else:
                self.stdout.write(self.style.WARNING(f'Дефект уже существует: {name}'))