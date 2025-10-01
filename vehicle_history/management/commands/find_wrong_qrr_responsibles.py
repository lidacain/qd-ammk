# vehicle_history/management/commands/find_wrong_qrr_responsibles.py
from collections import defaultdict
from typing import Iterable, Tuple, Dict, Any, List, Optional

from django.core.management.base import BaseCommand, CommandParser
from vehicle_history.models import VINHistory
from supplies.models import TraceData


# ключевые слова по брендам, которыми «помечены» правильные ответственные
BRAND_KEYWORDS = {
    "gwm":     ["gwm", "haval", "tank"],
    "chery":   ["chery"],
    "changan": ["changan"],
}

# ярлыки, которые не считаем ошибкой
IGNORE_LABELS = {
    "(в ожидании назначения)",
    "(в ожидании назначения)".lower(),
}


def normalize_brand(raw: Optional[str]) -> Optional[str]:
    """Приводим TraceData.brand к нашим ключам (gwm|chery|changan)."""
    if not raw:
        return None
    s = str(raw).strip().lower()
    if s.startswith("gwm") or "haval" in s or "tank" in s:
        return "gwm"
    if s.startswith("chery"):
        return "chery"
    if s.startswith("changan"):
        return "changan"
    return None


def has_own_brand(label: Optional[str], brand_key: Optional[str]) -> bool:
    """Есть ли в названии ответственного слово бренда VIN-а?"""
    if not label or not brand_key:
        return False
    lab = str(label).strip().lower()
    if lab in IGNORE_LABELS:
        return True
    return any(kw in lab for kw in BRAND_KEYWORDS.get(brand_key, []))


def scan_wrong_responsibles(
    brand_filter: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """
    Возвращает:
      rows   — построчный список несоответствий (каждый «чужой» ответственный — отдельная строка)
      by_vin — те же строки, сгруппированные по VIN
    """
    rows: List[Dict[str, Any]] = []
    by_vin: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    qs = VINHistory.objects.iterator()  # потоково
    for hist in qs:
        vin = hist.vin
        brand_raw = TraceData.objects.filter(vin_rk=vin).values_list("brand", flat=True).first()
        brand = normalize_brand(brand_raw)
        if not brand:
            continue
        if brand_filter and brand != brand_filter:
            continue

        history_data = hist.history or {}
        shop = history_data.get("Цех сборки") or {}
        # shop: { "Интерьер":[ {...}, ... ], "Экстерьер":[...], ... }
        for zone, posts in shop.items():
            for post in (posts or []):
                for defect in (post.get("defects") or []):
                    extra = defect.get("extra") or {}
                    responsibles = extra.get("qrr_responsibles") or []
                    for resp in responsibles:
                        if not has_own_brand(resp, brand):
                            rec = {
                                "vin": vin,
                                "brand": brand,
                                "zone": zone,
                                "post_id": post.get("id"),
                                "defect_id": defect.get("id"),
                                "defect_name": defect.get("name"),
                                "responsible": resp,
                            }
                            rows.append(rec)
                            by_vin[vin].append(rec)

    return rows, by_vin


class Command(BaseCommand):
    help = "Находит VIN, где у дефектов выбраны «чужие» QRR-ответственные (по бренду)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--brand",
            choices=["gwm", "chery", "changan"],
            help="Фильтровать только по одному бренду из TraceData.",
        )
        parser.add_argument(
            "--csv",
            metavar="PATH",
            help="Путь для выгрузки CSV (если не указать — просто печать в консоль).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Ограничить печать по VIN в консоли (0 — без ограничений).",
        )

    def handle(self, *args, **opts):
        brand_filter = opts.get("brand")
        rows, by_vin = scan_wrong_responsibles(brand_filter=brand_filter)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Всего несоответствий: {len(rows)}; уникальных VIN: {len(by_vin)}"
        ))

        # консольная сводка
        limit = int(opts.get("limit") or 0)
        for i, (vin, items) in enumerate(by_vin.items(), 1):
            if limit and i > limit:
                self.stdout.write(self.style.WARNING(f"... (обрезано по --limit={limit})"))
                break
            brand = items[0]["brand"] if items else "?"
            self.stdout.write(f"\n{i}. VIN: {vin} · бренд: {brand} · неверных ответственных: {len(items)}")
            for j, r in enumerate(items, 1):
                self.stdout.write(
                    f"   {j}) [{r['zone']}] defect_id={r['defect_id']} "
                    f"«{r['defect_name']}» -> «{r['responsible']}»"
                )

        # CSV (если попросили)
        csv_path = opts.get("csv")
        if csv_path:
            import csv
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["vin", "brand", "zone", "defect_id", "defect_name", "responsible"])
                for r in rows:
                    w.writerow([
                        r["vin"],
                        r["brand"],
                        r["zone"],
                        r["defect_id"],
                        (r.get("defect_name") or "").replace(",", " "),
                        (r.get("responsible") or "").replace(",", " "),
                    ])
            self.stdout.write(self.style.SUCCESS(f"\nCSV сохранён: {csv_path}"))