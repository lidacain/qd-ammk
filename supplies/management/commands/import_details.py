import pandas as pd
from django.core.management.base import BaseCommand
from supplies.models import Detail, Post

class Command(BaseCommand):
    help = "Импорт деталей из Excel в базу данных"

    def handle(self, *args, **kwargs):
        file_path = "/Users/adil/PycharmProjects/amm_server/factory_server/supplies/management/commands/ details.xlsx"  # Укажите путь к файлу
        xls = pd.ExcelFile(file_path)
        df = pd.read_excel(xls, sheet_name=0)  # Один лист

        # Убираем пустые строки и пробелы
        df = df.dropna().applymap(lambda x: x.strip() if isinstance(x, str) else x)

        # Получаем первые четыре поста
        posts = list(Post.objects.all()[:4])

        # Добавляем детали в базу данных и привязываем к постам
        for name in df.iloc[:, 0].dropna().unique():  # Берем данные из первого столбца
            detail, created = Detail.objects.get_or_create(name=name)
            if created:
                detail.posts.set(posts)  # Привязываем к первым четырем постам
                self.stdout.write(self.style.SUCCESS(f'Добавлена деталь: {name} и привязана к первым четырем постам'))
            else:
                self.stdout.write(self.style.WARNING(f'Деталь уже существует: {name}'))