# vehicle_history/management/commands/list_all_posts.py
from django.core.management.base import BaseCommand
from vehicle_history.models import VINHistory
import csv

POST_HINT_FIELDS = {
    "date", "date_added", "controller", "has_defect", "defects",
    "vin_number", "line", "inspection_duration_seconds", "photos", "comment", "grade", "unit"
}

def is_post_entries_list(value) -> bool:
    """
    Эвристика: значение является списком записей поста, если это list из dict,
    и хотя бы в одном dict есть характерные поля (date_added / controller / defects и т.п.)
    """
    if not isinstance(value, list):
        return False
    for item in value:
        if isinstance(item, dict) and (POST_HINT_FIELDS & set(item.keys())):
            return True
    return False

def collect_posts(obj, posts: set):
    """
    Рекурсивный обход любого JSON (dict/list) и сбор ключей, чьи значения похожи на список записей поста.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if is_post_entries_list(v):
                # k — это имя поста
                if isinstance(k, str) and k.strip():
                    posts.add(k.strip())
            # продолжим обход внутрь
            collect_posts(v, posts)
    elif isinstance(obj, list):
        for item in obj:
            collect_posts(item, posts)

class Command(BaseCommand):
    help = "Выводит все уникальные названия постов, когда-либо встречавшиеся в VINHistory.history."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            dest="csv_path",
            help="Путь к CSV-файлу для сохранения списка постов (необязательно).",
        )

    def handle(self, *args, **options):
        csv_path = options.get("csv_path")

        posts = set()
        qs = VINHistory.objects.only("history")

        for vh in qs.iterator():
            history = getattr(vh, "history", {}) or {}
            try:
                collect_posts(history, posts)
            except Exception as e:
                self.stderr.write(self.style.WARNING(f"⚠️ Пропуск записи: {e}"))

        posts_sorted = sorted(posts, key=lambda x: x.lower())
        self.stdout.write(self.style.SUCCESS(f"Найдено уникальных постов: {len(posts_sorted)}"))
        for name in posts_sorted:
            self.stdout.write(name)

        if csv_path:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["post"])
                for name in posts_sorted:
                    writer.writerow([name])
            self.stdout.write(self.style.SUCCESS(f"CSV сохранён: {csv_path}"))