# vehicle_history/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify
from django.utils import timezone

from .models import VINHistory


def _ensure_ids(history: dict, vin: str) -> bool:
    """
    Проставляет недостающие ID и индексы в history.
    Возвращает True, если были изменения.
    """
    changed = False
    if not isinstance(history, dict):
        return changed

    for zone, posts in (history or {}).items():
        if not isinstance(posts, dict):
            continue
        zone_slug = slugify(zone, allow_unicode=True)

        for post, entries in posts.items():
            if not isinstance(entries, list):
                continue
            post_slug = slugify(post, allow_unicode=True)

            # максимальный существующий индекс записи в этом посте
            max_entry_idx = 0
            for e in entries:
                try:
                    max_entry_idx = max(max_entry_idx, int(e.get("entry_index", 0)))
                except Exception:
                    pass

            for e in entries:
                # === ENTRY ID ===
                if "entry_index" not in e:
                    max_entry_idx += 1
                    e["entry_index"] = max_entry_idx
                    changed = True

                entry_idx = int(e["entry_index"])
                expected_entry_id = f"{vin}-{zone_slug}-{post_slug}-{entry_idx}"
                if e.get("id") != expected_entry_id:
                    e["id"] = expected_entry_id
                    changed = True

                # === DEFECT IDs ===
                defects = e.get("defects", [])
                if not isinstance(defects, list):
                    continue

                max_defect_idx = 0
                for d in defects:
                    try:
                        max_defect_idx = max(max_defect_idx, int(d.get("defect_index", 0)))
                    except Exception:
                        pass

                for d in defects:
                    if "defect_index" not in d:
                        max_defect_idx += 1
                        d["defect_index"] = max_defect_idx
                        changed = True

                    defect_idx = int(d["defect_index"])
                    expected_defect_id = f"{vin}-{zone_slug}-{post_slug}-{entry_idx}-{defect_idx}"
                    if d.get("id") != expected_defect_id:
                        d["id"] = expected_defect_id
                        changed = True

    return changed


@receiver(post_save, sender=VINHistory)
def assign_ids_on_save(sender, instance: VINHistory, created, **kwargs):
    """
    После каждого save() у VINHistory дописываем отсутствующие ID/индексы.
    Важно: сохраняем через queryset.update(), чтобы НЕ вызывать сигнал повторно.
    """
    history = instance.history or {}
    if _ensure_ids(history, instance.vin):
        # update(), а не save(), чтобы избежать рекурсии сигнала
        VINHistory.objects.filter(pk=instance.pk).update(
            history=history,
            updated_at=timezone.now()
        )