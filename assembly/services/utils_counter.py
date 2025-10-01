from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from typing import Iterable, List, Optional, Dict, Any, Tuple

from django.db.models import QuerySet
from django.utils.timezone import make_aware, get_current_timezone
from django.db.models import Q

from vehicle_history.models import AssemblyPassLog
from supplies.models import TraceData

# --- Helpers ----------------------------------------------------------------

def _to_date(d: Optional[Any]) -> Optional[date]:
    """
    Convert str 'YYYY-MM-DD' or datetime/date to date. Returns None if empty.
    """
    if d is None or d == "":
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, str):
        # naive parse: 'YYYY-MM-DD'
        try:
            y, m, dd = map(int, d[:10].split("-"))
            return date(y, m, dd)
        except Exception:
            raise ValueError(f"Invalid date string: {d!r}")
    raise TypeError(f"Unsupported date type: {type(d)}")

def _aware_bounds(start: Optional[date], end: Optional[date]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Given naive dates, produce timezone-aware datetime bounds [start, end] inclusive in user's TZ.
    End bound becomes the last microsecond of the day.
    """
    tz = get_current_timezone()
    start_dt = make_aware(datetime.combine(start, time.min), tz) if start else None
    if end:
        # inclusive end of day
        end_dt = make_aware(datetime.combine(end + timedelta(days=1), time.min), tz) - timedelta(microseconds=1)
    else:
        end_dt = None
    return start_dt, end_dt

def _unique_preserve_order(vins: Iterable[str]) -> List[str]:
    """
    Deduplicate VINs preserving first occurrence order.
    """
    return list(OrderedDict((v, None) for v in vins if v).keys())

# --- Public API --------------------------------------------------------------

def counter_vins(
    *,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    start_date: Optional[date | str] = None,
    end_date: Optional[date | str] = None,
    distinct: bool = True,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Вернёт список VIN-номеров и их количество по посту-счётчику AssemblyPassLog
    с фильтрами по бренду/модели и диапазону дат.

    Параметры:
      - brand: фильтр по TraceData.brand (нечувствительный к регистру), опционально
      - model: фильтр по TraceData.model (нечувствительный к регистру), опционально
      - start_date, end_date: дата(ы) как date или 'YYYY-MM-DD'; обе включительно
      - distinct: если True — возвращает уникальные VIN (по последнему скану)
      - limit: ограничить длину списка VIN (после дедупликации/сортировки)

    Возвращает:
      {
        "count": int,            # количество VIN (уникальных, если distinct=True)
        "vins":  List[str],      # список VINов (уникальных, отсортированных по времени скана убыв.)
      }
    """
    # 1) Базовый queryset логов
    qs: QuerySet[AssemblyPassLog] = AssemblyPassLog.objects.all()

    # 2) Фильтр по датам (inclusive)
    s = _to_date(start_date)
    e = _to_date(end_date)
    s_dt, e_dt = _aware_bounds(s, e)
    if s_dt and e_dt:
        qs = qs.filter(scanned_at__range=(s_dt, e_dt))
    elif s_dt:
        qs = qs.filter(scanned_at__gte=s_dt)
    elif e_dt:
        qs = qs.filter(scanned_at__lte=e_dt)

    # 3) Фильтр по бренду/модели через TraceData
    if brand or model:
        td = TraceData.objects.all()
        if brand:
            td = td.filter(brand__iexact=str(brand).strip())
        if model:
            td = td.filter(model__iexact=str(model).strip())
        vins_sub = td.values_list("vin_rk", flat=True)
        qs = qs.filter(vin__in=vins_sub)

    # 4) Получаем VINы упорядоченные по времени (последние сверху)
    vins_qs = qs.order_by("-scanned_at").values_list("vin", flat=True)
    vins_list = list(vins_qs)

    if distinct:
        vins_list = _unique_preserve_order(vins_list)

    if limit is not None and limit >= 0:
        vins_list = vins_list[:limit]

    return {
        "count": len(vins_list),
        "vins": vins_list,
    }

def counter_vins_for_day(
    *,
    day: date | str,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    distinct: bool = True,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Удобный шорткат: статистика за конкретный день (локальная TZ).
    """
    d = _to_date(day)
    if not d:
        raise ValueError("Parameter 'day' is required")
    return counter_vins(
        brand=brand,
        model=model,
        start_date=d,
        end_date=d,
        distinct=distinct,
        limit=limit,
    )

# === Vehicle History based counters =========================================
# Карта "пост -> агрегированная зона" дана для справки — нам важны ключи (названия постов)
POST_AREA_MAPPING = {
    "Зазоры и перепады": "Первая инспекция",
    "Экстерьер": "Первая инспекция",
    "Интерьер": "Первая инспекция",
    "Багажник": "Первая инспекция",
    "Мотор": "Первая инспекция",
    "Функцонал": "Первая инспекция",

    "Геометрия колес": "Тестовая линия",
    "Регулировка света фар и калибровка руля": "Тестовая линия",
    "Тормозная система": "Тестовая линия",
    "Underbody": "Тестовая линия",
    "ADAS": "Тестовая линия",
    "AVM": "Тестовая линия",
    "Герметичность кузова": "Тестовая линия",

    "Диагностика": "Финал + Тест трек",
    "Тест трек": "Финал + Тест трек",
    "Документация": "Финал + Тест трек",
}

def _parse_iso_dt_isoaware(s: str) -> Optional[datetime]:
    """
    Безопасный парсер ISO 8601 (включая смещение), возвращает datetime (aware, если смещение есть).
    """
    if not s:
        return None
    try:
        # Python 3.11+: fromisoformat понимает смещения вида +05:00
        return datetime.fromisoformat(s)
    except Exception:
        return None

def _iter_history_entries(history: Dict[str, Any]) -> Iterable[Tuple[str, datetime, str]]:
    """
    Итерируем по всем элементам истории VINHistory.
    Возвращаем кортежи: (post_name, date_added_dt, vin_number)
    """
    if not isinstance(history, dict):
        return
    for zone_name, zone_block in history.items():
        if not isinstance(zone_block, dict):
            continue
        for post_name, entries in zone_block.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                dt = _parse_iso_dt_isoaware(entry.get("date_added", ""))
                vin_num = (entry.get("vin_number") or "").strip().upper()
                yield post_name, dt, vin_num

def counter_vins_from_vehicle_history(
    *,
    posts: Optional[Iterable[str]] = None,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    start_date: Optional[date | str] = None,
    end_date: Optional[date | str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Возвращает уникальные VIN и их количество среди тех, которые прошли ХОТЯ БЫ ОДИН
    из указанных постов в VINHistory (JSON), с фильтрами по бренду/модели и датам.

    - posts: список названий постов; если None, берём ключи из POST_AREA_MAPPING.
    - brand/model: фильтры по TraceData.
    - start_date/end_date: включительно; сравниваем по entry['date_added'].
    - limit: ограничение на длину возвращаемого списка VIN (после сортировки).

    Результат:
      {"count": int, "vins": [VIN1, VIN2, ...]}  -- VIN упорядочены по последней дате входящего поста (убыв.)
    """
    from vehicle_history.models import VINHistory  # локальный импорт чтобы избегать циклов

    posts_set = set(posts) if posts is not None else set(POST_AREA_MAPPING.keys())
    if not posts_set:
        return {"count": 0, "vins": []}

    # Фильтруем VIN по бренду/модели через TraceData
    td_qs = TraceData.objects.all()
    if brand:
        td_qs = td_qs.filter(brand__iexact=str(brand).strip())
    if model:
        td_qs = td_qs.filter(model__iexact=str(model).strip())
    if brand or model:
        vin_pool = set(td_qs.values_list("vin_rk", flat=True))
        if not vin_pool:
            return {"count": 0, "vins": []}
        vh_qs = VINHistory.objects.filter(vin__in=vin_pool)
    else:
        vh_qs = VINHistory.objects.all()

    # Датные границы (aware)
    s = _to_date(start_date)
    e = _to_date(end_date)
    s_dt, e_dt = _aware_bounds(s, e)

    latest_dt_by_vin: Dict[str, datetime] = {}

    for vh in vh_qs.only("vin", "history"):
        hist = vh.history or {}
        for post_name, dt, vin_num in _iter_history_entries(hist):
            if post_name not in posts_set:
                continue

            # Определяем VIN для учёта
            vin_effective = (vin_num or vh.vin or "").strip().upper()
            if not vin_effective:
                continue

            # Дата фильтра
            if dt is None:
                continue
            # Если границы заданы, проверим включительно
            if s_dt and dt < s_dt:
                continue
            if e_dt and dt > e_dt:
                continue

            # Апдейтим "последнюю дату" для VIN
            prev = latest_dt_by_vin.get(vin_effective)
            if prev is None or (dt and dt > prev):
                latest_dt_by_vin[vin_effective] = dt

    # Сортируем VIN по последнему попаданию (убывание)
    vins_sorted = sorted(latest_dt_by_vin.items(), key=lambda x: (x[1] or datetime.min), reverse=True)
    vins = [v for v, _ in vins_sorted]
    if limit is not None and limit >= 0:
        vins = vins[:limit]

    return {"count": len(vins), "vins": vins}


# --- Специализированный helper для поста "Документация" ---------------------
def counter_vins_documentation(
    *,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    start_date: Optional[date | str] = None,
    end_date: Optional[date | str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Специализированная функция для поста «Документация».
    Возвращает уникальные VIN и их количество за выбранный период с фильтрами бренда и модели.

    Параметры идентичны counter_vins_from_vehicle_history, но пост фиксирован: "Документация".
    """
    return counter_vins_from_vehicle_history(
        posts=["Документация"],
        brand=brand,
        model=model,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )




