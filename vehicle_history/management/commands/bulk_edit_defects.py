from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Dict, Set, Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.timezone import now

from vehicle_history.models import VINHistory, VINHistoryBackup


ZONE_ASSEMBLY = "Цех сборки"
ALLOWED_GRADES = {"V1+", "V1", "V2", "V3"}


def _read_lines_file(p: Optional[str]) -> List[str]:
    if not p:
        return []
    path = Path(p)
    if not path.exists():
        raise CommandError(f"File not found: {p}")

    # PowerShell (>) often creates UTF-16LE files; try a few encodings in order.
    encodings = ("utf-8", "utf-8-sig", "utf-16", "utf-16le", "utf-16be", "cp1251", "mbcs")
    last_err: Exception | None = None
    for enc in encodings:
        try:
            text = path.read_text(encoding=enc)
            lines = [ln.strip() for ln in text.splitlines()]
            return [ln for ln in lines if ln]
        except Exception as e:
            last_err = e
            continue

    # If nothing worked, surface a clear error to the user
    raise CommandError(
        f"Cannot read VIN list from {p}. Tried encodings: {', '.join(encodings)}. "
        f"Last error: {last_err}"
    )


def _split_csv(val: Optional[str]) -> List[str]:
    if not val:
        return []
    return [x.strip() for x in val.split(",") if x.strip()]


def _iter_defects(
    vh: VINHistory,
    zone: str,
    post_filter: Set[str] | None,
    defect_ids: Set[str] | None,
    name_contains: str | None,
    name_equals: str | None,
    unit_equals: str | None,
    unit_contains: str | None,
) -> Iterable[tuple[str, str, dict, dict]]:
    """
    Возвращает (post_name, entry_id, entry_dict, defect_dict) подходящие под фильтры.
    """
    data = vh.history or {}
    zone_map: Dict[str, List[dict]] = data.get(zone, {}) or {}

    name_eq = (name_equals or "").strip().lower() if name_equals else None
    unit_eq = (unit_equals or "").strip().lower() if unit_equals else None
    unit_sub = (unit_contains or "").strip().lower() if unit_contains else None
    name_sub = (name_contains or "").strip().lower() if name_contains else None

    for post_name, entries in zone_map.items():
        if post_filter and post_name not in post_filter:
            continue
        for entry in (entries or []):
            for defect in (entry.get("defects") or []):
                if defect_ids and defect.get("id") not in defect_ids:
                    continue
                d_name = (defect.get("name") or "").strip().lower()
                d_unit = (defect.get("unit") or "").strip().lower()
                if name_eq and d_name != name_eq:
                    continue
                if name_sub and name_sub not in d_name:
                    continue
                if unit_eq and d_unit != unit_eq:
                    continue
                if unit_sub and unit_sub not in d_unit:
                    continue
                yield post_name, entry.get("id"), entry, defect


class Command(BaseCommand):
    """
    Массовое редактирование дефектов в VINHistory.

    Примеры:

    # По конкретным defect_id — поставить extra.qrr_grade=V1 и переписать основной grade:
    python manage.py bulk_edit_defects --vin MXMDB21BXSK097335 \
      --ids MXMDB21BXSK097335-цех-сборки-интерьер-2-1,MXMDB21BXSK097335-цех-сборки-интерьер-2-2 \
      --set-qrr-grade V1 --overwrite-main --confirm

    # По постам (Chassis и Интерьер) — выставить грейд только в extra (без изменения основного grade):
    python manage.py bulk_edit_defects --vin MXMDB21BXSK097335 \
      --posts Chassis,Интерьер --set-qrr-grade V2 --confirm

    # Поменять unit всем дефектам VIN на посте Underbody, где имя содержит «царапина»:
    python manage.py bulk_edit_defects --vin MXMDB21BXSK097335 \
      --posts Underbody --name-contains царапина \
      --set-unit "Другое Подвеска/ходовая часть" --confirm

    # Несколько VIN-ов из файла (по одному в строке):
    python manage.py bulk_edit_defects --vin-file vins.txt --posts Chassis --set-qrr-grade V1 --confirm

    По умолчанию зона --zone="Цех сборки".
    Без --confirm команда выполняется как DRY-RUN (ничего не пишет).
    """

    help = "Массовое изменение полей дефектов VINHistory (QRR). Без --confirm — dry-run."

    def add_arguments(self, parser):
        # что отбирать
        parser.add_argument("--vin", help="VIN или список VIN через запятую")
        parser.add_argument("--vin-file", help="Файл со списком VIN (по одному на строку)")
        parser.add_argument("--ids", help="Список defect_id через запятую (фильтр)")
        parser.add_argument("--posts", help="Список постов через запятую (фильтр)")
        parser.add_argument("--zone", default=ZONE_ASSEMBLY, help='Зона/цех (по умолчанию "Цех сборки")')
        parser.add_argument("--name-contains", help="Фильтр по подстроке в названии дефекта (регистр не важен)")
        parser.add_argument("--name-equals", help="Точное совпадение имени дефекта (без учета регистра)")
        parser.add_argument("--unit", dest="unit_equals", help="Точное совпадение детали/юнита (без учета регистра)")
        parser.add_argument("--unit-contains", help="Подстрока в названии детали/юнита (без учета регистра)")

        # что менять
        parser.add_argument("--set-qrr-grade", help="Записать extra.qrr_grade=VALUE (V1+/V1/V2/V3)")
        parser.add_argument("--overwrite-main", action="store_true",
                            help="Если указан --set-qrr-grade, также перезаписать основной defect['grade']")
        parser.add_argument("--set-unit", help="Записать defect['unit']=VALUE")
        parser.add_argument("--set-comment", help="Записать defect['comment']=VALUE (перезапишет)")
        parser.add_argument("--set-name", help="Записать defect['name']=VALUE")

        # мета-инфо
        parser.add_argument("--by", dest="set_by",
                            help="Кто меняет (extra.qrr_grade_changed_by / qrr_set_by)")
        parser.add_argument("--why", dest="just",
                            help="Обоснование (extra.qrr_grade_justification)")
        parser.add_argument("--responsibles", help="extra.qrr_responsibles имена (через запятую)")
        parser.add_argument("--responsibles-ids", help="extra.qrr_responsibles_ids (через запятую чисел)")

        parser.add_argument("--confirm", action="store_true", help="Выполнить изменения (иначе dry-run)")

    def handle(self, *args, **opts):
        vins: Set[str] = set(_split_csv(opts.get("vin")))
        vins |= set(_read_lines_file(opts.get("vin_file")))
        vins = {v.strip().upper() for v in vins if v.strip()}
        if not vins:
            raise CommandError("Укажите хотя бы один VIN через --vin или --vin-file")

        defect_ids = set(_split_csv(opts.get("ids"))) or None
        posts = set(_split_csv(opts.get("posts"))) or None
        zone = opts.get("zone") or ZONE_ASSEMBLY
        name_contains = opts.get("name_contains")
        name_equals = opts.get("name_equals")
        unit_equals = opts.get("unit_equals")
        unit_contains = opts.get("unit_contains")

        set_qrr_grade = opts.get("set_qrr_grade")
        if set_qrr_grade:
            set_qrr_grade = set_qrr_grade.strip().upper()
            if set_qrr_grade not in ALLOWED_GRADES:
                raise CommandError(f"--set-qrr-grade должен быть одним из {sorted(ALLOWED_GRADES)}")

        overwrite_main = bool(opts.get("overwrite_main"))
        set_unit = opts.get("set_unit")
        set_comment = opts.get("set_comment")
        set_name = opts.get("set_name")
        set_by = opts.get("set_by")
        just = opts.get("just")
        resp_names = _split_csv(opts.get("responsibles"))
        resp_ids = [int(x) for x in _split_csv(opts.get("responsibles_ids"))] if opts.get("responsibles_ids") else []

        do_write = bool(opts.get("confirm"))

        total_matched = 0
        total_changed = 0

        with transaction.atomic():
            for vin in sorted(vins):
                try:
                    vh = VINHistory.objects.select_for_update().get(vin=vin)
                except VINHistory.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"[{vin}] VINHistory not found"))
                    continue

                matched_ids: List[str] = []

                for post_name, entry_id, entry, defect in _iter_defects(
                    vh, zone, posts, defect_ids,
                    name_contains, name_equals, unit_equals, unit_contains
                ):
                    total_matched += 1
                    matched_ids.append(defect.get("id") or "?")

                    before = {
                        "grade": defect.get("grade"),
                        "unit": defect.get("unit"),
                        "comment": defect.get("comment"),
                        "extra": defect.get("extra") or {},
                    }

                    changed = False
                    extra = defect.get("extra") or {}
                    if not isinstance(extra, dict):
                        extra = {}

                    # 1) qrr grade (+ мета)
                    if set_qrr_grade:
                        if extra.get("qrr_grade") != set_qrr_grade:
                            extra["qrr_grade"] = set_qrr_grade
                            extra["qrr_grade_changed_at"] = now().isoformat()
                            if set_by:
                                extra["qrr_grade_changed_by"] = set_by
                            if just:
                                extra["qrr_grade_justification"] = just
                            changed = True
                        if defect.get("grade") != set_qrr_grade:
                            defect["grade"] = set_qrr_grade
                            changed = True

                    # 2) unit
                    if set_unit is not None and defect.get("unit") != set_unit:
                        defect["unit"] = set_unit
                        changed = True

                    # 2b) name
                    if set_name is not None and defect.get("name") != set_name:
                        defect["name"] = set_name
                        changed = True

                    # 3) comment
                    if set_comment is not None and (defect.get("comment") != set_comment):
                        defect["comment"] = set_comment
                        changed = True

                    # 4) responsibles
                    if resp_names:
                        extra["qrr_responsibles"] = resp_names
                        changed = True
                    if resp_ids:
                        extra["qrr_responsibles_ids"] = resp_ids
                        changed = True
                    if set_by and not set_qrr_grade:
                        # просто фиксируем, кто назначил
                        extra["qrr_set_by"] = set_by
                        extra["qrr_set_at"] = now().isoformat()
                        changed = True

                    if changed:
                        defect["extra"] = extra  # записать обратно
                        total_changed += 1

                        # backup
                        try:
                            VINHistoryBackup.objects.create(
                                vin=vin,
                                post=post_name,
                                zone=zone,
                                entry={"type": "defect", "entry_id": entry_id, "data": before},
                                action="edit",
                            )
                        except Exception:
                            # бэкап не должен валить транзакцию
                            pass

                if matched_ids:
                    self.stdout.write(self.style.SUCCESS(f"[{vin}] matched defects: {len(matched_ids)}"))
                else:
                    self.stdout.write(f"[{vin}] matched defects: 0")

                if do_write and matched_ids:
                    vh.save(update_fields=["history", "updated_at"])

            if not do_write:
                # отменяем транзакцию и показываем сводку
                raise CommandError(
                    f"DRY-RUN: matched={total_matched}, would change={total_changed}. "
                    f"Запусти с --confirm, чтобы применить."
                )

        self.stdout.write(self.style.SUCCESS(f"Done. matched={total_matched}, changed={total_changed}"))