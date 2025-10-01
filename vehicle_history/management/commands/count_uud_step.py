# vehicle_history/management/commands/count_uud_step.py
from django.core.management.base import BaseCommand, CommandError
from vehicle_history.models import VINHistory


def _get(o, k, d=None):
    try:
        return (o or {}).get(k, d)
    except Exception:
        return d


def _has_step(entry, step_num: int) -> bool:
    """
    Проверяет, отмечен ли шаг step_num для данной записи УУД.
    Смотрим и в extra_data, и на верхнем уровне (на всякий случай).
    Для шага считаем валидным наличие *_at и одного из *_by / *_user / *_by_login.
    """
    extra = _get(entry, "extra_data", {}) or {}
    at = extra.get(f"step{step_num}_at") or entry.get(f"step{step_num}_at")
    by = (
        extra.get(f"step{step_num}_by")
        or extra.get(f"step{step_num}_user")
        or extra.get(f"step{step_num}_by_login")
        or entry.get(f"step{step_num}_by")
        or entry.get(f"step{step_num}_user")
        or entry.get(f"step{step_num}_by_login")
    )
    return bool(at and by)


class Command(BaseCommand):
    help = (
        "Считает уникальные VIN, которые 'остались' на указанном шаге УУД: "
        "шаг N выполнен, а шагов > N нет."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--step",
            type=int,
            default=1,
            choices=[1, 2, 3, 4],
            help="Какой шаг УУД считать (по умолчанию 1).",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="Вывести VIN-номера, соответствующие критерию.",
        )

    def handle(self, *args, **opts):
        target_step = opts["step"]
        list_vins = opts["list"]

        vins_at_target_only = set()

        # Проходим по всем VINHistory
        for history in VINHistory.objects.all().iterator():
            uud_entries = _get(_get(history.history, "УУД"), "УУД", []) or []
            if not uud_entries:
                continue

            # Флаги наличия шагов (по всему VIN, если хотя бы в одной записи он отмечен)
            has = {1: False, 2: False, 3: False, 4: False}
            for entry in uud_entries:
                for s in (1, 2, 3, 4):
                    if not has[s] and _has_step(entry, s):
                        has[s] = True
                # мини-оптимизация — если все уже True, можно выйти
                if all(has.values()):
                    break

            # Условие "остался на шаге N":
            #  - шаг N есть
            #  - НЕТ ни одного шага больше N
            if has[target_step] and not any(has[s] for s in range(target_step + 1, 5)):
                vins_at_target_only.add(history.vin)

        total = len(vins_at_target_only)
        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Уникальных машин на УУД шаге {target_step} (без шагов выше): {total}"
            )
        )

        if list_vins and vins_at_target_only:
            self.stdout.write("VIN-номера:")
            for v in sorted(vins_at_target_only):
                self.stdout.write(v)
