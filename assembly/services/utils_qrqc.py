from datetime import date, datetime, timedelta
from typing import Optional, Sequence, Set, Tuple
from django.db.models.functions import Lower

import json
from django.utils.dateparse import parse_datetime
from django.utils.timezone import localtime, is_aware

from vehicle_history.models import VINHistory
from supplies.models import TraceData

ZONE_ASSEMBLY = "Цех сборки"

# Карта брендов к значениям в TraceData.brand
BRAND_MAP = {
    "gwm": ["haval", "tank"],
    "chery": ["chery"],
    "changan": ["changan"],
}

# --- V3 include/exclude switch ---
INCLUDE_V3_DEFAULT = False  # по умолчанию V3 исключаем из расчётов

def _is_v3(grade: str) -> bool:
    return str(grade).strip().upper() == "V3"


def _grade_allowed_single(grade_value: str, selected_grade: Optional[str], include_v3: bool) -> bool:
    """
    Для функций с одиночным фильтром по грейду (grade: Optional[str]).
    Возвращает True, если дефект с данным грейдом должен учитываться.
    """
    g = str(grade_value or "").strip()
    if not g:
        return False
    if not include_v3 and _is_v3(g):
        return False
    if selected_grade is not None and g != selected_grade:
        return False
    return True

# ---------------- Core date helpers ----------------
def _iso_week_bounds(iso_year: int, iso_week: int) -> tuple[date, date]:
    """Понедельник..Воскресенье для ISO-недели."""
    start = date.fromisocalendar(iso_year, iso_week, 1)
    end = date.fromisocalendar(iso_year, iso_week, 7)
    return start, end


def _parse_entry_date(raw_date: str | None) -> Optional[date]:
    """Берём первые 10 символов 'YYYY-MM-DD'."""
    if not raw_date:
        return None
    try:
        return datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
    except Exception:
        return None

# ---------------- VIN filtering ----------------
def _normalize_brand_models(
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
) -> Tuple[Optional[Sequence[str]], Optional[Sequence[str]]]:
    """
    Возвращает (brands_list_or_None, models_list_or_None) для фильтрации TraceData.
    brand — slug 'gwm'|'chery'|'changan' (или None), models — список имён моделей (или None).
    """
    brands_list = None
    if brand:
        brands_list = BRAND_MAP.get(brand.lower(), [brand.lower()])
    return brands_list, (list(models) if models else None)


def _get_vins_by_filters(
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
) -> Set[str]:
    """VIN-ы, ограниченные brand/models если заданы, иначе все VIN."""
    brands_list, models_list = _normalize_brand_models(brand, models)
    qs = TraceData.objects.all()

    # регистронезависимая фильтрация brand/model
    annotations = {}
    if brands_list:
        annotations["_brand_l"] = Lower("brand")
    if models_list:
        annotations["_model_l"] = Lower("model")
    if annotations:
        qs = qs.annotate(**annotations)

    if brands_list:
        qs = qs.filter(_brand_l__in=[b.lower() for b in brands_list])
    if models_list:
        qs = qs.filter(_model_l__in=[m.lower() for m in models_list])
    return set(qs.values_list("vin_rk", flat=True))


def _histories_for_vins(vins: Set[str]):
    """Возвращает QuerySet VINHistory по набору VIN; если пусто — .none()."""
    if not vins:
        return VINHistory.objects.none()
    return VINHistory.objects.filter(vin__in=vins)

# ---------------- Aggregation helpers ----------------
def _entry_passes_filters(
    entry: dict,
    target_date: Optional[date],
    start_d: Optional[date],
    end_d: Optional[date],
    post: Optional[str],
    grade: Optional[str],
) -> bool:
    """
    Проверка только по дате (точный день или интервал). Пост фильтруется снаружи; грейд не участвует.
    """
    d = _parse_entry_date(entry.get("date_added"))
    if not d:
        return False

    if target_date is not None:
        return d == target_date
    if (start_d and d < start_d) or (end_d and d > end_d):
        return False
    return True


def _aggregate_period_with_filters(
    histories,
    start_d: Optional[date] = None,
    end_d: Optional[date] = None,
    target_date: Optional[date] = None,
    post: Optional[str] = None,
    grade: Optional[str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> dict:
    """
    Сводка по дню/диапазону дат. Возвращает агрегат за весь интервал + по дням:
    {
      "inspected": int, "defects": int, "dpu": float, "str": float,
      "inspected_vins": set[str], "defective_vins": set[str], "offline_vins": set[str],
      "days": { date: {"vins": set[str], "defects": int, "offline_defects": int, "offline_vins": set[str]} }
    }
    """
    # Подготовка диапазона
    if target_date is not None:
        start_d = end_d = target_date

    per_day = {}  # date -> {"vins": set(), "defects": int, "offline_defects": int, "offline_vins": set()}

    def ensure_day(d: date):
        if d not in per_day:
            per_day[d] = {"vins": set(), "defects": 0, "offline_defects": 0, "offline_vins": set()}

    inspected_vins: Set[str] = set()
    defective_vins: Set[str] = set()
    defects_total = 0
    offline_vins_total: Set[str] = set()

    for h in histories.iterator():
        zone_data = (h.history or {}).get(ZONE_ASSEMBLY, {})
        posts_iter = [post] if post else zone_data.keys()

        # чтобы VIN попадал в "inspected" только если была релевантная запись
        seen_any_for_vin = False
        seen_defect_for_vin = False

        for p in posts_iter:
            entries = zone_data.get(p, []) or []
            for entry in entries:
                d = _parse_entry_date(entry.get("date_added"))
                if not d:
                    continue
                if start_d and d < start_d:
                    continue
                if end_d and d > end_d:
                    continue

                # На этом этапе запись релевантна по дате/посту.
                ensure_day(d)
                per_day[d]["vins"].add(h.vin)
                seen_any_for_vin = True

                # Считаем дефекты: фильтруем по грейду, если он задан, и по include_v3
                defects_list = entry.get("defects") or []
                filtered_defects = [
                    df for df in defects_list
                    if _grade_allowed_single(df.get("grade"), grade, include_v3)
                ]

                # Считаем дефекты: каждый элемент списка = 1 дефект (quantity игнорируем)
                if filtered_defects:
                    seen_defect_for_vin = True
                    defects_total += len(filtered_defects)
                    per_day[d]["defects"] += len(filtered_defects)

                    # Оффлайн-дефекты (now track VINs with at least one offline defect)
                    offline_cnt = 0
                    has_offline_for_vin_this_entry = False
                    for df in filtered_defects:
                        if str(df.get("repair_type", "")).lower() == "offline":
                            offline_cnt += 1
                            has_offline_for_vin_this_entry = True
                    per_day[d]["offline_defects"] += offline_cnt
                    if has_offline_for_vin_this_entry:
                        per_day[d]["offline_vins"].add(h.vin)
                        offline_vins_total.add(h.vin)

        if seen_any_for_vin:
            inspected_vins.add(h.vin)
        if seen_defect_for_vin:
            defective_vins.add(h.vin)

    inspected = len(inspected_vins)
    dpu_val = round(defects_total / inspected, 2) if inspected else 0.0

    # STR now uses count of unique VINs with at least one offline defect
    offline_vins_count = len(offline_vins_total)
    str_val = 0.0 if inspected == 0 else max(
        0.0, min(100.0, round(100.0 - ((offline_vins_count / inspected) * 100.0), 2))
    )
    return {
        "inspected": inspected,
        "defects": defects_total,
        "dpu": dpu_val,
        "str": str_val,
        "inspected_vins": inspected_vins,
        "defective_vins": defective_vins,
        "offline_vins": offline_vins_total,
        "days": per_day,
    }

# ---------------- Public API ----------------

def qrqc_daily_series_6weeks(
    target_date: date,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grade: Optional[str] = None,
    post: Optional[str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """
    Возвращает массив по дням за текущую ISO-неделю target_date и 5 предыдущих недель (итого 42 дня).
    Каждый элемент:
    {
      "date": date,
      "unique_vins": int,
      "defects": int,
      "offline_defects": int,
      "dpu": float,   # defects / unique_vins (0 если unique_vins==0)
      "str": float,   # 100 - ((offline_vins_count / unique_vins) * 100); 100 если offline_vins_count==0
                      # Здесь offline_vins_count — число VIN с хотя бы одним offline дефектом за день.
    }
    Фильтры применяются ко всем метрикам (brand/models/post/grade).
    """
    if not isinstance(target_date, date):
        raise ValueError("target_date должен быть date")

    vins = _get_vins_by_filters(brand=brand, models=models)
    histories = _histories_for_vins(vins)

    # Начало 6-недельного окна: понедельник недели target_date минус 5 недель
    iso_year, iso_week, _ = target_date.isocalendar()
    week_start, _ = _iso_week_bounds(iso_year, iso_week)
    window_start = week_start - timedelta(weeks=5)
    window_end = week_start + timedelta(days=6)  # конец текущей недели (воскресенье)

    agg = _aggregate_period_with_filters(
        histories, start_d=window_start, end_d=window_end, post=post, grade=grade,
        include_v3=include_v3,
    )
    per_day = agg["days"]

    # Собираем 42 дня подряд
    result = []
    cur = window_start
    while cur <= window_end:
        day_data = per_day.get(cur, {"vins": set(), "defects": 0, "offline_defects": 0, "offline_vins": set()})
        vins_count = len(day_data["vins"])
        defects = day_data["defects"]
        offline = day_data["offline_defects"]
        offline_vins_count = len(day_data.get("offline_vins", set()))

        dpu = round(defects / vins_count, 2) if vins_count else 0.0
        str_val = 0.0 if vins_count == 0 else max(
            0.0, min(100.0, round(100.0 - ((offline_vins_count / vins_count) * 100.0), 2))
        )

        result.append({
            "date": cur,
            "unique_vins": vins_count,
            "defects": defects,
            "offline_defects": offline,
            "dpu": dpu,
            "str": str_val,
        })
        cur += timedelta(days=1)

    return result

# ---------------- Generic daily series for arbitrary past window ----------------

def qrqc_daily_series_last_n_days(
    target_date: date,
    days: int,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grade: Optional[str] = None,
    post: Optional[str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """
    Универсальная функция: возвращает дневной ряд длиной N дней, заканчивающийся target_date
    (включительно). Метрики аналогичны qrqc_daily_series_6weeks: unique_vins, defects,
    offline_defects, dpu, str.

    Используется фронтом для построения графиков "За месяц/пол года/год" с возможной
    последующей агрегацией по неделям/месяцам на клиенте.
    """
    if not isinstance(target_date, date):
        raise ValueError("target_date должен быть date")
    if days <= 0:
        return []

    # Границы окна: [start_d .. end_d], обе включительно
    end_d = target_date
    start_d = end_d - timedelta(days=days - 1)

    vins = _get_vins_by_filters(brand=brand, models=models)
    histories = _histories_for_vins(vins)

    agg = _aggregate_period_with_filters(
        histories,
        start_d=start_d,
        end_d=end_d,
        post=post,
        grade=grade,
        include_v3=include_v3,
    )
    per_day = agg["days"]

    # Собираем последовательность по всем календарным дням окна
    out: list[dict] = []
    cur = start_d
    while cur <= end_d:
        drow = per_day.get(cur, {"vins": set(), "defects": 0, "offline_defects": 0, "offline_vins": set()})
        vins_count = len(drow.get("vins", set()))
        defects = drow.get("defects", 0)
        offline_def = drow.get("offline_defects", 0)
        offline_vins_count = len(drow.get("offline_vins", set()))

        dpu = round(defects / vins_count, 2) if vins_count else 0.0
        str_val = 0.0 if vins_count == 0 else max(
            0.0, min(100.0, round(100.0 - ((offline_vins_count / vins_count) * 100.0), 2))
        )

        out.append({
            "date": cur,
            "unique_vins": vins_count,
            "defects": defects,
            "offline_defects": offline_def,
            "dpu": dpu,
            "str": str_val,
        })
        cur += timedelta(days=1)

    return out


def qrqc_last_month_daily(
    target_date: date,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grade: Optional[str] = None,
    post: Optional[str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """Дневной ряд за последние 30 дней (включая target_date)."""
    return qrqc_daily_series_last_n_days(
        target_date=target_date,
        days=30,
        brand=brand,
        models=models,
        grade=grade,
        post=post,
        include_v3=include_v3,
    )


def qrqc_last_halfyear_daily(
    target_date: date,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grade: Optional[str] = None,
    post: Optional[str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """Дневной ряд за последние 180 дней (включая target_date)."""
    return qrqc_daily_series_last_n_days(
        target_date=target_date,
        days=180,
        brand=brand,
        models=models,
        grade=grade,
        post=post,
        include_v3=include_v3,
    )


def qrqc_last_year_daily(
    target_date: date,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grade: Optional[str] = None,
    post: Optional[str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """Дневной ряд за последние 365 дней (включая target_date)."""
    return qrqc_daily_series_last_n_days(
        target_date=target_date,
        days=365,
        brand=brand,
        models=models,
        grade=grade,
        post=post,
        include_v3=include_v3,
    )

def _split_into_weeks_6w(series: list[dict], week_start: date) -> list[list[dict]]:
    """
    Вспомогательная: разбивает 42-дневную серию на 6 недель по 7 дней,
    начиная с week_start-5 недель (0-й блок) и заканчивая текущей неделей (5-й блок).
    """
    # ожидаем, что series упорядочен по возрастанию дат и покрывает окно:
    # [week_start-5w .. week_start+6]
    blocks: list[list[dict]] = []
    cur = week_start - timedelta(weeks=5)
    idx = 0
    # сопоставим индексы дат для надёжности
    by_date = {row["date"]: row for row in series}
    for w in range(6):
        days = []
        for d in range(7):
            dd = cur + timedelta(days=d)
            days.append(by_date.get(dd, {"date": dd, "unique_vins": 0, "defects": 0, "offline_defects": 0, "offline_vins": set(), "dpu": 0.0, "str": 0.0}))
        blocks.append(days)
        cur += timedelta(weeks=1)
    return blocks


def qrqc_prev5_weeks_avg(
    target_date: date,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grade: Optional[str] = None,
    post: Optional[str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """
    Возвращает 5 ПРЕДЫДУЩИХ ISO‑недель (без текущей) с усреднёнными метриками по активным дням.
    Активный день — когда есть хоть какая активность: unique_vins>0 или defects>0 или offline_defects>0 или offline_vins>0.
    Для каждой недели считаем средние по активным дням:
      - avg_unique_vins
      - avg_dpu  (defects / unique_vins)
      - avg_str  (100 - (offline_vins_count / unique_vins * 100))
        Здесь offline_vins_count — число VIN с хотя бы одним offline дефектом за день
    Если активных дней нет — все значения 0.0, days_used=0.
    """
    if not isinstance(target_date, date):
        raise ValueError("target_date должен быть date")

    # Понедельник текущей ISO‑недели
    iso_year, iso_week, _ = target_date.isocalendar()
    cur_week_start, _ = _iso_week_bounds(iso_year, iso_week)

    out: list[dict] = []

    # Строго W-5 .. W-1
    for i in range(5, 0, -1):
        week_start = cur_week_start - timedelta(weeks=i)
        week_end = week_start + timedelta(days=6)
        y, w, _ = week_start.isocalendar()

        vins = _get_vins_by_filters(brand=brand, models=models)
        histories = _histories_for_vins(vins)
        agg = _aggregate_period_with_filters(
            histories,
            start_d=week_start,
            end_d=week_end,
            post=post,
            grade=grade,
            include_v3=include_v3,
        )
        per_day = agg["days"]

        # Активные дни внутри недели
        active_days = []
        d = week_start
        while d <= week_end:
            dd = per_day.get(d, {"vins": set(), "defects": 0, "offline_defects": 0, "offline_vins": set()})
            offline_vins_count = len(dd.get("offline_vins", set()))
            if dd["vins"] or dd["defects"] or dd["offline_defects"] or offline_vins_count:
                vins_count = len(dd["vins"]) or 0
                defects = dd["defects"]
                dpu = round(defects / vins_count, 2) if vins_count else 0.0
                str_val = 0.0 if vins_count == 0 else max(
                    0.0, min(100.0, round(100.0 - ((offline_vins_count / vins_count) * 100.0), 2))
                )
                active_days.append({"unique_vins": vins_count, "dpu": dpu, "str": str_val})
            d += timedelta(days=1)

        days_used = len(active_days)
        if days_used == 0:
            avg_unique = 0.0
            avg_dpu = 0.0
            avg_str = 0.0
        else:
            avg_unique = round(sum(x["unique_vins"] for x in active_days) / days_used, 2)
            avg_dpu = round(sum(x["dpu"] for x in active_days) / days_used, 2)
            avg_str = round(sum(x["str"] for x in active_days) / days_used, 2)

        out.append({
            "iso_year": y,
            "iso_week": w,
            "start": week_start,
            "end": week_end,
            "avg_unique_vins": avg_unique,
            "avg_dpu": avg_dpu,
            "avg_str": avg_str,
            "days_used": days_used,
        })

    return out


def qrqc_prev5_weeks_totals(
    target_date: date,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grade: Optional[str] = None,
    post: Optional[str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """
    Возвращает СУММАРНЫЕ метрики по 5 ПРЕДЫДУЩИМ ISO-неделям (без текущей):
      - unique_vins: количество уникальных VIN за неделю (унион по Пн..Вс)
      - defects: сумма дефектов за неделю (фильтруется по grade, если задан)
      - offline_defects: сумма оффлайн-дефектов за неделю (legacy, для совместимости)
      - dpu: defects / unique_vins (0 если unique_vins == 0)
      - str: 100 - ((offline_vins_count / unique_vins) * 100)   [с клиппингом в 0..100; если unique_vins==0 → 100]
        Здесь offline_vins_count — число VIN с хотя бы одним offline дефектом за неделю

    Фильтры: brand/models/post/grade.
    Возвращает список по возрастанию недели.
    """
    if not isinstance(target_date, date):
        raise ValueError("target_date должен быть date")

    # Понедельник текущей ISO‑недели
    iso_year, iso_week, _ = target_date.isocalendar()
    cur_week_start, _ = _iso_week_bounds(iso_year, iso_week)

    out: list[dict] = []

    # Недели строго W-5 .. W-1 (по возрастанию)
    for i in range(5, 0, -1):
        week_start = cur_week_start - timedelta(weeks=i)
        week_end   = week_start + timedelta(days=6)
        y, w, _ = week_start.isocalendar()

        # VIN → histories
        vins = _get_vins_by_filters(brand=brand, models=models)
        histories = _histories_for_vins(vins)

        # Агрегируем неделю единым вызовом
        agg = _aggregate_period_with_filters(
            histories,
            start_d=week_start,
            end_d=week_end,
            post=post,
            grade=grade,
            include_v3=include_v3,
        )

        unique_vins = len(agg["inspected_vins"])              # уникальные VIN за всю неделю
        total_defects = agg["defects"]                         # дефекты за неделю (с учётом grade)
        offline_vins_total = len(agg.get("offline_vins", set()))

        dpu = round(total_defects / unique_vins, 2) if unique_vins else 0.0
        # Было: str_val = 100.0 if unique_vins == 0 else ...
        str_val = 0.0 if unique_vins == 0 else max(
            0.0, min(100.0, round(100.0 - ((offline_vins_total / unique_vins) * 100.0), 2))
        )

        out.append({
            "iso_year": y,
            "iso_week": w,
            "start": week_start,
            "end": week_end,
            "unique_vins": unique_vins,
            "defects": total_defects,
            "offline_defects": sum(d["offline_defects"] for d in agg["days"].values()),  # legacy field
            "dpu": dpu,
            "str": str_val,
        })

    return out






# ---------------- New helpers for multi-filter breakdowns (posts / grades / models) ----------------

# V3 limiter helper for multi-grade filters
def _grade_allowed_multi(grade_value, grades_set: Optional[set[str]], include_v3: bool) -> bool:
    """
    Returns True if the defect grade should be counted considering optional grades_set
    (lowercased values) and the global V3 include/exclude switch.
    """
    g = str(grade_value or "").strip()
    if not g:
        return False
    # respect global V3 switch
    if not include_v3 and _is_v3(g):
        return False
    # if a grades filter is provided, it is lowercased; compare in lower
    if grades_set is not None and g.lower() not in grades_set:
        return False
    return True

def _normalize_seq(val) -> Optional[set[str]]:
    """
    Accepts None, a single string, or a sequence of strings and returns a
    lowercase set (or None if no filter).
    """
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip()
        return set([s.lower()]) if s else None
    # sequence
    out = {str(x).strip().lower() for x in val if str(x).strip()}
    return out or None


def _iter_entries_for_period(histories, start_d: Optional[date], end_d: Optional[date], posts_set: Optional[set[str]]):
    """
    Yields tuples (vin, d, post, entry_dict) for entries that fall into [start_d .. end_d]
    and match posts_set (if provided).
    """
    for h in histories.iterator():
        zone_data = (h.history or {}).get(ZONE_ASSEMBLY, {})
        for post_name, entries in zone_data.items():
            post_name_l = str(post_name).lower()
            if posts_set is not None and post_name_l not in posts_set:
                continue
            for entry in (entries or []):
                d = _parse_entry_date(entry.get("date_added"))
                if not d:
                    continue
                if start_d and d < start_d:
                    continue
                if end_d and d > end_d:
                    continue
                yield h.vin, d, post_name, entry


def _vin_to_model_map(vins: Set[str]) -> dict[str, str]:
    """
    Returns mapping VIN -> model (as stored in TraceData.model, original case).
    Missing models are mapped to ''.
    """
    if not vins:
        return {}
    rows = TraceData.objects.filter(vin_rk__in=vins).values_list("vin_rk", "model")
    return {vin: (model or "") for vin, model in rows}

def qrqc_current_week_daily(
    target_date: date,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grade: Optional[str] = None,
    post: Optional[str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    if not isinstance(target_date, date):
        raise ValueError("target_date должен быть date")

    iso_year, iso_week, _ = target_date.isocalendar()
    return qrqc_week_daily(
        iso_year=iso_year,
        iso_week=iso_week,
        brand=brand,
        models=models,
        grade=grade,
        post=post,
        include_v3=include_v3,
    )


# --- New functions inserted after qrqc_current_week_daily ---
def qrqc_week_daily(
    *,
    iso_year: int,
    iso_week: int,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grade: Optional[str] = None,
    post: Optional[str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """
    Возвращает дневной ряд (Пн..Вс) для произвольной ISO‑недели iso_year/iso_week.
    Формат элементов ряда идентичен qrqc_daily_series_6weeks: {date, unique_vins, defects, offline_defects, dpu, str}.
    """
    if not isinstance(iso_year, int) or not isinstance(iso_week, int):
        raise ValueError("iso_year и iso_week должны быть int")

    week_start, week_end = _iso_week_bounds(iso_year, iso_week)

    vins = _get_vins_by_filters(brand=brand, models=models)
    histories = _histories_for_vins(vins)

    agg = _aggregate_period_with_filters(
        histories,
        start_d=week_start,
        end_d=week_end,
        post=post,
        grade=grade,
        include_v3=include_v3,
    )
    per_day = agg["days"]

    out: list[dict] = []
    cur = week_start
    while cur <= week_end:
        dd = per_day.get(cur, {"vins": set(), "defects": 0, "offline_defects": 0, "offline_vins": set()})
        vins_cnt = len(dd.get("vins", set()))
        defects = dd.get("defects", 0)
        offline_vins_cnt = len(dd.get("offline_vins", set()))
        offline_def = dd.get("offline_defects", 0)

        dpu = round(defects / vins_cnt, 2) if vins_cnt else 0.0
        str_val = 0.0 if vins_cnt == 0 else max(
            0.0, min(100.0, round(100.0 - ((offline_vins_cnt / vins_cnt) * 100.0), 2))
        )
        out.append({
            "date": cur,
            "unique_vins": vins_cnt,
            "defects": defects,
            "offline_defects": offline_def,
            "dpu": dpu,
            "str": str_val,
        })
        cur += timedelta(days=1)
    return out


def qrqc_day_daily(
    *,
    target_date: date,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grade: Optional[str] = None,
    post: Optional[str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """Возвращает метрики строго за один день target_date в формате списка из одного элемента."""
    if not isinstance(target_date, date):
        raise ValueError("target_date должен быть date")

    vins = _get_vins_by_filters(brand=brand, models=models)
    histories = _histories_for_vins(vins)

    agg = _aggregate_period_with_filters(
        histories,
        target_date=target_date,
        post=post,
        grade=grade,
        include_v3=include_v3,
    )
    dd = agg["days"].get(target_date, {"vins": set(), "defects": 0, "offline_defects": 0, "offline_vins": set()})
    vins_cnt = len(dd.get("vins", set()))
    defects = dd.get("defects", 0)
    offline_vins_cnt = len(dd.get("offline_vins", set()))
    offline_def = dd.get("offline_defects", 0)

    dpu = round(defects / vins_cnt, 2) if vins_cnt else 0.0
    str_val = 0.0 if vins_cnt == 0 else max(
        0.0, min(100.0, round(100.0 - ((offline_vins_cnt / vins_cnt) * 100.0), 2))
    )
    return [{
        "date": target_date,
        "unique_vins": vins_cnt,
        "defects": defects,
        "offline_defects": offline_def,
        "dpu": dpu,
        "str": str_val,
    }]


def qrqc_daily_series_range(
    *,
    start_d: date,
    end_d: date,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grade: Optional[str] = None,
    post: Optional[str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """
    Универсальный дневной ряд для произвольного периода [start_d..end_d] (обе границы включительно).
    Удобно для режимов «за месяц»/«за год», где фронт передаёт готовые даты.
    """
    if not isinstance(start_d, date) or not isinstance(end_d, date):
        raise ValueError("start_d и end_d должны быть date")
    if start_d > end_d:
        start_d, end_d = end_d, start_d

    vins = _get_vins_by_filters(brand=brand, models=models)
    histories = _histories_for_vins(vins)

    agg = _aggregate_period_with_filters(
        histories,
        start_d=start_d,
        end_d=end_d,
        post=post,
        grade=grade,
        include_v3=include_v3,
    )
    per_day = agg["days"]

    out: list[dict] = []
    cur = start_d
    while cur <= end_d:
        dd = per_day.get(cur, {"vins": set(), "defects": 0, "offline_defects": 0, "offline_vins": set()})
        vins_cnt = len(dd.get("vins", set()))
        defects = dd.get("defects", 0)
        offline_vins_cnt = len(dd.get("offline_vins", set()))
        offline_def = dd.get("offline_defects", 0)
        dpu = round(defects / vins_cnt, 2) if vins_cnt else 0.0
        str_val = 0.0 if vins_cnt == 0 else max(
            0.0, min(100.0, round(100.0 - ((offline_vins_cnt / vins_cnt) * 100.0), 2))
        )
        out.append({
            "date": cur,
            "unique_vins": vins_cnt,
            "defects": defects,
            "offline_defects": offline_def,
            "dpu": dpu,
            "str": str_val,
        })
        cur += timedelta(days=1)
    return out

def qrqc_by_posts(
    *,
    target_date: Optional[date] = None,
    start_d: Optional[date] = None,
    end_d: Optional[date] = None,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grades: Optional[Sequence[str] | str] = None,
    posts: Optional[Sequence[str] | str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:

    """
    Постовая сводка по цеху сборки: DPU, STR, проверено машин и VIN-ы этих машин по каждому посту.

    Период можно задать одной датой (target_date) или интервалом [start_d..end_d].
    Фильтры: brand/models/grades/posts (могут быть одиночными строками или последовательностью).
    V3 defects are excluded unless include_v3=True.

    Возвращает список словарей по постам:
      {
        "post": str,
        "inspected": int,
        "vins": list[str],
        "defects": int,
        "offline_defects": int,  # число VIN с хотя бы одним offline дефектом
        "dpu": float,
        "str": float
      }
    """
    if target_date is not None:
        start_d = end_d = target_date
    if start_d is None or end_d is None:
        raise ValueError("Нужно задать target_date или оба start_d и end_d")

    vins = _get_vins_by_filters(brand=brand, models=models)
    histories = _histories_for_vins(vins)

    posts_set = _normalize_seq(posts)
    grades_set = _normalize_seq(grades)

    per_post: dict[str, dict] = {}  # post -> counters

    for vin, d, post_name, entry in _iter_entries_for_period(histories, start_d, end_d, posts_set):
        rec = per_post.setdefault(post_name, {"vins": set(), "defects": 0, "offline_defects": 0, "offline_vins": set()})
        rec["vins"].add(vin)

        defects_list = entry.get("defects") or []
        defects_list = [
            df for df in defects_list
            if _grade_allowed_multi(df.get("grade"), grades_set, include_v3)
        ]

        if defects_list:
            rec["defects"] += len(defects_list)
            if any(str(df.get("repair_type", "")).lower() == "offline" for df in defects_list):
                rec["offline_defects"] += 1  # keep field for backward compatibility (represents VINs count now)
                rec["offline_vins"].add(vin)

    # finalize
    out: list[dict] = []
    for post_name, rec in sorted(per_post.items(), key=lambda kv: str(kv[0]).lower()):
        inspected = len(rec["vins"])
        defects = rec["defects"]
        offline = len(rec.get("offline_vins", set()))
        dpu = round(defects / inspected, 2) if inspected else 0.0
        str_val = 0.0 if inspected == 0 else max(
            0.0, min(100.0, round(100.0 - ((offline / inspected) * 100.0), 2))
        )
        out.append({
            "post": post_name,
            "inspected": inspected,
            "vins": sorted(rec["vins"]),
            "defects": defects,
            "offline_defects": offline,
            "dpu": dpu,
            "str": str_val,
        })
    return out


def qrqc_defects_by_grade(
    *,
    target_date: Optional[date] = None,
    start_d: Optional[date] = None,
    end_d: Optional[date] = None,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    posts: Optional[Sequence[str] | str] = None,
    grades: Optional[Sequence[str] | str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """
    Возвращает распределение дефектов по грейдам и VIN-ы с такими дефектами по цеху сборки.
    Количество (quantity) не учитываем — каждая запись в списке defects считается одним дефектом.

    Если параметр `grades` задан — считаем только по указанным грейдам. Иначе по всем, которые встретились.
    Фильтры: brand/models/posts + период (target_date или [start_d..end_d]).
    V3 defects are excluded unless include_v3=True.
    """
    if target_date is not None:
        start_d = end_d = target_date
    if start_d is None or end_d is None:
        raise ValueError("Нужно задать target_date или оба start_d и end_d")

    vins = _get_vins_by_filters(brand=brand, models=models)
    histories = _histories_for_vins(vins)

    posts_set = _normalize_seq(posts)
    grades_set = _normalize_seq(grades)

    by_grade: dict[str, dict] = {}  # grade -> {"defects": int, "vins": set()}

    for vin, d, post_name, entry in _iter_entries_for_period(histories, start_d, end_d, posts_set):
        defects_list = entry.get("defects") or []
        for df in defects_list:
            g = str(df.get("grade", "")).strip()
            if not _grade_allowed_multi(g, grades_set, include_v3):
                continue
            rec = by_grade.setdefault(g, {"defects": 0, "vins": set()})
            rec["defects"] += 1  # quantity игнорируем
            rec["vins"].add(vin)

    out: list[dict] = []
    for grade_name, rec in sorted(by_grade.items(), key=lambda kv: kv[0]):
        out.append({
            "grade": grade_name,
            "defects": rec["defects"],
            "vins": sorted(rec["vins"]),
        })
    return out


def qrqc_by_models(
    *,
    target_date: Optional[date] = None,
    start_d: Optional[date] = None,
    end_d: Optional[date] = None,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    grades: Optional[Sequence[str] | str] = None,
    posts: Optional[Sequence[str] | str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """
    Модельная сводка по цеху сборки: DPU, STR, проверено машин и VIN-ы по каждой модели.
    Фильтры: brand/models (ограничивают парк VIN), posts/grades, период.
    V3 defects are excluded unless include_v3=True.

    Возвращает список словарей:
      {
        "model": str,
        "inspected": int,
        "vins": list[str],
        "defects": int,
        "offline_defects": int,  # число VIN с хотя бы одним offline дефектом
        "dpu": float,
        "str": float
      }
    """
    if target_date is not None:
        start_d = end_d = target_date
    if start_d is None or end_d is None:
        raise ValueError("Нужно задать target_date или оба start_d и end_d")

    vins = _get_vins_by_filters(brand=brand, models=models)
    histories = _histories_for_vins(vins)

    posts_set = _normalize_seq(posts)
    grades_set = _normalize_seq(grades)

    vin2model = _vin_to_model_map(vins)
    per_model: dict[str, dict] = {}  # model -> counters

    for vin, d, post_name, entry in _iter_entries_for_period(histories, start_d, end_d, posts_set):
        model = vin2model.get(vin, "") or ""
        rec = per_model.setdefault(model, {"vins": set(), "defects": 0, "offline_defects": 0, "offline_vins": set()})
        rec["vins"].add(vin)

        defects_list = entry.get("defects") or []
        defects_list = [
            df for df in defects_list
            if _grade_allowed_multi(df.get("grade"), grades_set, include_v3)
        ]

        if defects_list:
            rec["defects"] += len(defects_list)
            if any(str(df.get("repair_type", "")).lower() == "offline" for df in defects_list):
                rec["offline_defects"] += 1  # keep field for backward compatibility
                rec["offline_vins"].add(vin)

    out: list[dict] = []
    for model_name, rec in sorted(per_model.items(), key=lambda kv: (kv[0] or "").lower()):
        inspected = len(rec["vins"])
        defects = rec["defects"]
        offline = len(rec.get("offline_vins", set()))
        dpu = round(defects / inspected, 2) if inspected else 0.0
        str_val = 0.0 if inspected == 0 else max(
            0.0, min(100.0, round(100.0 - ((offline / inspected) * 100.0), 2))
        )
        out.append({
            "model": model_name,
            "inspected": inspected,
            "vins": sorted(rec["vins"]),
            "defects": defects,
            "offline_defects": offline,
            "dpu": dpu,
            "str": str_val,
        })
    return out


# ---------------- TOP tables ----------------

_GRADE_PRIORITY = {
    "V1+": 0,
    "V1": 1,
    "V2": 2,
    "V3": 3,
}


def _collect_defect_counters(
    *,
    target_date: Optional[date] = None,
    start_d: Optional[date] = None,
    end_d: Optional[date] = None,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    posts: Optional[Sequence[str] | str] = None,
    grades: Optional[Sequence[str] | str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> dict[tuple[str, str, str], int]:
    """
    Служебная: собирает счётчики дефектов по ключу (detail, defect, grade).
    Количество (quantity) игнорируется — один элемент массива defects = 1 дефект.
    Возвращает: {(detail, defect, grade): count}
    V3 defects are excluded unless include_v3=True.
    """
    if target_date is not None:
        start_d = end_d = target_date
    if start_d is None or end_d is None:
        raise ValueError("Нужно задать target_date или оба start_d и end_d")

    vins = _get_vins_by_filters(brand=brand, models=models)
    histories = _histories_for_vins(vins)

    posts_set = _normalize_seq(posts)
    grades_set = _normalize_seq(grades)

    counters: dict[tuple[str, str, str], int] = {}
    for _vin, _d, _post_name, entry in _iter_entries_for_period(histories, start_d, end_d, posts_set):
        defects_list = entry.get("defects") or []
        for df in defects_list:
            grade = str(df.get("grade", "")).strip()
            if not _grade_allowed_multi(grade, grades_set, include_v3):
                continue
            # In our schema: unit = part (деталь), name = defect (название дефекта).
            # Keep backward compatibility by falling back to legacy keys.
            detail = str(df.get("unit") or df.get("detail") or "").strip()
            defect = str(df.get("name") or df.get("defect") or "").strip()
            key = (detail, defect, grade)
            counters[key] = counters.get(key, 0) + 1
    return counters


# --- rich defect collector ---
def _collect_defect_counters_rich(
    *,
    target_date: Optional[date] = None,
    start_d: Optional[date] = None,
    end_d: Optional[date] = None,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    posts: Optional[Sequence[str] | str] = None,
    grades: Optional[Sequence[str] | str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> dict[tuple[str, str, str], dict]:
    """
    Полный сборщик по ключу (detail, defect, grade) с:
      - count: количество дефектов (поштучно, quantity игнорируем),
      - responsibles: распределённые веса по ответственным QRR,
      - ids: список ID дефектов (как в df["id"]),
      - vins: множество VIN-ов, у которых встречался такой дефект этого грейда.
    """
    if target_date is not None:
        start_d = end_d = target_date
    if start_d is None or end_d is None:
        raise ValueError("Нужно задать target_date или оба start_d и end_d")

    vins = _get_vins_by_filters(brand=brand, models=models)
    histories = _histories_for_vins(vins)

    posts_set = _normalize_seq(posts)
    grades_set = _normalize_seq(grades)

    out: dict[tuple[str, str, str], dict] = {}

    for vin, _d, _post_name, entry in _iter_entries_for_period(histories, start_d, end_d, posts_set):
        defects_list = entry.get("defects") or []
        for df in defects_list:
            grade = str(df.get("grade", "")).strip()
            if not _grade_allowed_multi(grade, grades_set, include_v3):
                continue

            detail = str(df.get("unit") or df.get("detail") or "").strip()
            defect = str(df.get("name") or df.get("defect") or "").strip()
            key = (detail, defect, grade)

            # bucket init
            b = out.setdefault(key, {"count": 0, "responsibles": {}, "ids": [], "vins": set()})

            # 1) count (+1 за каждый элемент)
            b["count"] += 1

            # 2) responsibles with split weight
            extra = df.get("extra") or {}
            responsibles = extra.get("qrr_responsibles") or []
            resp_names: list[str] = [str(r).strip() for r in responsibles if str(r).strip()]
            if not resp_names:
                resp_names = ["(В ожидании назначения)"]
            weight = 1.0 / len(resp_names)
            for r in resp_names:
                b["responsibles"][r] = round(b["responsibles"].get(r, 0.0) + weight, 6)

            # 3) ids (если есть)
            df_id = df.get("id")
            if df_id:
                b["ids"].append(str(df_id))

            # 4) vins
            b["vins"].add(vin)

    return out

# --- New: Defect counters by responsible ---
def _collect_defect_counters_by_responsible(
    *,
    target_date: Optional[date] = None,
    start_d: Optional[date] = None,
    end_d: Optional[date] = None,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    posts: Optional[Sequence[str] | str] = None,
    grades: Optional[Sequence[str] | str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> dict[tuple[str, str, str], dict[str, float]]:
    """
    NEW: Считывает дефекты и распределяет "вес" каждого дефекта между ответственными QRR.

    На каждый элемент defects считается базовый вес = 1. Если у дефекта указаны несколько
    ответственных (extra.qrr_responsibles = ["A", "B", "C"]), то вес распределяется поровну:
        1 / len(responsibles) на каждого.
    Если список ответственных пустой или отсутствует, вся единица веса относится к
    специальной группе "(В ожидании назначения)".

    Возвращает словарь:
        { (detail, defect, grade): { responsible_name: total_weight, ... }, ... }

    Фильтрация идентична `_collect_defect_counters`:
    - Период задаётся target_date или [start_d..end_d]
    - Ограничения по brand/models/posts/grades
    - V3 исключается, если include_v3 = False
    """
    if target_date is not None:
        start_d = end_d = target_date
    if start_d is None or end_d is None:
        raise ValueError("Нужно задать target_date или оба start_d и end_d")

    vins = _get_vins_by_filters(brand=brand, models=models)
    histories = _histories_for_vins(vins)

    posts_set = _normalize_seq(posts)
    grades_set = _normalize_seq(grades)

    out: dict[tuple[str, str, str], dict[str, float]] = {}

    for _vin, _d, _post_name, entry in _iter_entries_for_period(histories, start_d, end_d, posts_set):
        defects_list = entry.get("defects") or []
        for df in defects_list:
            grade = str(df.get("grade", "")).strip()
            if not _grade_allowed_multi(grade, grades_set, include_v3):
                continue

            # Деталь/дефект (поддерживаем старые ключи)
            detail = str(df.get("unit") or df.get("detail") or "").strip()
            defect = str(df.get("name") or df.get("defect") or "").strip()
            key = (detail, defect, grade)

            # Ответственные из QRR
            extra = df.get("extra") or {}
            responsibles = extra.get("qrr_responsibles") or []
            # Нормализуем к строковым именам
            resp_names: list[str] = [str(r).strip() for r in responsibles if str(r).strip()]
            if not resp_names:
                resp_names = ["(В ожидании назначения)"]

            weight = 1.0 / len(resp_names)

            bucket = out.setdefault(key, {})
            for r in resp_names:
                bucket[r] = round(bucket.get(r, 0.0) + weight, 6)  # аккумулируем с округлением до 1e-6

    return out

def qrqc_defects_weight_by_responsible(
    *,
    target_date: Optional[date] = None,
    start_d: Optional[date] = None,
    end_d: Optional[date] = None,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    posts: Optional[Sequence[str] | str] = None,
    grades: Optional[Sequence[str] | str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """
    Плоский вывод весов дефектов по ответственным.

    Возвращает список словарей:
      {
        "detail": str,
        "defect": str,
        "grade": str,
        "responsible": str,
        "weight": float
      }

    Полезно для построения сводных таблиц/диаграмм (можно сгруппировать по responsible).
    """
    nested = _collect_defect_counters_by_responsible(
        target_date=target_date,
        start_d=start_d,
        end_d=end_d,
        brand=brand,
        models=models,
        posts=posts,
        grades=grades,
        include_v3=include_v3,
    )
    rows: list[dict] = []
    for (detail, defect, grade), bucket in nested.items():
        for responsible, weight in bucket.items():
            rows.append({
                "detail": detail,
                "defect": defect,
                "grade": grade,
                "responsible": responsible,
                "weight": round(float(weight), 6),
            })
    # Стабильная сортировка: по ответственному, затем по весу убыв.
    rows.sort(key=lambda x: (x["responsible"].lower(), -x["weight"], x["detail"].lower(), x["defect"].lower(), _GRADE_PRIORITY.get(x["grade"], 999)))
    return rows


def qrqc_top_defects_by_grades(
    *,
    target_date: Optional[date] = None,
    start_d: Optional[date] = None,
    end_d: Optional[date] = None,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    posts: Optional[Sequence[str] | str] = None,
    grades: Optional[Sequence[str] | str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """
    Данные для таблицы «ТОП дефектов по грейдам».
    В выборку попадают все грейды (или только указанные через `grades`).
    Сортировка: по важности грейда (V1+ → V1 → V2 → V3), затем по убыванию количества.
    Возвращает список словарей: {"detail": str, "defect": str, "count": int, "grade": str}  # detail = df.unit, defect = df.name
    V3 defects are excluded unless include_v3=True.
    """
    data = _collect_defect_counters_rich(
        target_date=target_date, start_d=start_d, end_d=end_d,
        brand=brand, models=models, posts=posts, grades=grades,
        include_v3=include_v3,
    )

    def sort_key(item: tuple[tuple[str, str, str], dict]):
        (_detail, _defect, grade), rec = item
        pr = _GRADE_PRIORITY.get(grade, 999)
        return (pr, -rec["count"], _detail.lower(), _defect.lower())

    items = sorted(data.items(), key=sort_key)
    out: list[dict] = []
    for (detail, defect, grade), rec in items:
        out.append({
            "detail": detail,
            "defect": defect,
            "count": rec["count"],
            "grade": grade,
            "responsibles": rec["responsibles"],
            "defect_ids": rec["ids"],
            "vins": sorted(rec["vins"]),
        })
    return out



def qrqc_top_defects_by_mass(
    *,
    target_date: Optional[date] = None,
    start_d: Optional[date] = None,
    end_d: Optional[date] = None,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    posts: Optional[Sequence[str] | str] = None,
    grades: Optional[Sequence[str] | str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """
    Данные для таблицы «ТОП дефектов по массовости».
    По умолчанию берётся только грейд V2 (как «массовый»). Если `grades` указан — используем его.
    Сортировка: по убыванию количества, затем по названию детали/дефекта.
    Возвращает список словарей: {"detail": str, "defect": str, "count": int, "grade": str}  # detail = df.unit, defect = df.name
    V3 defects are excluded unless include_v3=True.
    """
    grades = grades if grades is not None else ["V2"]

    data = _collect_defect_counters_rich(
        target_date=target_date, start_d=start_d, end_d=end_d,
        brand=brand, models=models, posts=posts, grades=grades,
        include_v3=include_v3,
    )

    items = sorted(
        data.items(),
        key=lambda kv: (-kv[1]["count"], kv[0][0].lower(), kv[0][1].lower(), _GRADE_PRIORITY.get(kv[0][2], 999))
    )
    out: list[dict] = []
    for (detail, defect, grade), rec in items:
        out.append({
            "detail": detail,
            "defect": defect,
            "count": rec["count"],
            "grade": grade,
            "responsibles": rec["responsibles"],
            "defect_ids": rec["ids"],
            "vins": sorted(rec["vins"]),
        })
    return out


# --- DPU by responsible ---
def qrqc_dpu_by_responsible(
    *,
    target_date: Optional[date] = None,
    start_d: Optional[date] = None,
    end_d: Optional[date] = None,
    brand: Optional[str] = None,
    models: Optional[Sequence[str]] = None,
    posts: Optional[Sequence[str] | str] = None,
    grades: Optional[Sequence[str] | str] = None,
    include_v3: bool = INCLUDE_V3_DEFAULT,
) -> list[dict]:
    """
    DPU по ответственным:
      - Суммируем "вес" дефектов, распределённый между ответственными (1/N на запись),
        с учётом фильтров brand/models/posts/grades и периода.
      - Делим на количество уникальных VIN, ПРОШЕДШИХ осмотр в выбранных постах за период.
        (VIN считается осмотренным, если есть хотя бы ОДНА запись entry по постам и датам,
         даже если в ней нет дефектов.)

    Возвращает список словарей, отсортированный по DPU (убыв.):
      {
        "responsible": str,        # имя группы ответственого (или "(В ожидании назначения)")
        "defects_weight": float,   # суммарный вес дефектов по этому ответственному
        "inspected": int,          # уникальные VIN (делитель)
        "dpu": float               # defects_weight / inspected (0.0 если inspected == 0)
      }
    """
    # Определяем период
    if target_date is not None:
        start_d = end_d = target_date
    if start_d is None or end_d is None:
        raise ValueError("Нужно задать target_date или оба start_d и end_d")

    # VIN парк по brand/models
    vins = _get_vins_by_filters(brand=brand, models=models)
    histories = _histories_for_vins(vins)

    posts_set = _normalize_seq(posts)
    grades_set = _normalize_seq(grades)

    # Аккумуляторы
    inspected_vins: set[str] = set()
    weights_by_resp: dict[str, float] = {}

    # Обходим все релевантные записи
    for vin, _d, _post_name, entry in _iter_entries_for_period(histories, start_d, end_d, posts_set):
        # VIN прошёл осмотр (по датам/постам) — добавляем независимо от наличия дефектов
        inspected_vins.add(vin)

        # Считаем веса дефектов по ответственным (с учётом грейдов/в3-флага)
        defects_list = entry.get("defects") or []
        for df in defects_list:
            grade = str(df.get("grade", "")).strip()
            if not _grade_allowed_multi(grade, grades_set, include_v3):
                continue
            extra = df.get("extra") or {}
            responsibles = extra.get("qrr_responsibles") or []
            resp_names = [str(r).strip() for r in responsibles if str(r).strip()]
            if not resp_names:
                resp_names = ["(В ожидании назначения)"]
            w = 1.0 / len(resp_names)
            for r in resp_names:
                weights_by_resp[r] = round(weights_by_resp.get(r, 0.0) + w, 6)

    inspected = len(inspected_vins)

    # Готовим вывод
    out: list[dict] = []
    for resp, w in weights_by_resp.items():
        dpu_val = round((w / inspected), 6) if inspected else 0.0
        out.append({
            "responsible": resp,
            "defects_weight": round(float(w), 6),
            "inspected": inspected,
            "dpu": dpu_val,
        })

    # Добавляем агрегат "all" = все дефекты / все уникальные VIN (за выбранные фильтры)
    total_weight = round(sum(weights_by_resp.values()), 6)
    all_dpu = round((total_weight / inspected), 6) if inspected else 0.0
    out.append({
        "responsible": "ALL",
        "defects_weight": total_weight,
        "inspected": inspected,
        "dpu": all_dpu,
    })

    # Сортировка: по DPU (desc), затем по весу (desc), затем по имени
    out.sort(key=lambda x: (-x["dpu"], -x["defects_weight"], x["responsible"].lower()))
    return out




def get_defect_details_many(vin: str, defect_ids: list[str]) -> list[dict]:
    """Возвращает список данных по нескольким дефектам VIN-а.
    Принимает список ID (могут повторяться/с пробелами) и возвращает
    полные записи по каждому найденному ID — в формате, совместимом с QRR карточками.
    """
    # Нормализуем вход
    ids_set = {str(x).strip() for x in (defect_ids or []) if str(x).strip()}
    if not vin or not ids_set:
        return []

    try:
        hist = VINHistory.objects.get(vin=vin)
    except VINHistory.DoesNotExist:
        return []

    results: list[dict] = []
    history_data = hist.history or {}
    zone_data = history_data.get(ZONE_ASSEMBLY, {}) or {}

    for post_name, entries in zone_data.items():
        for entry in (entries or []):
            entry_id = entry.get("id")
            controller = entry.get("controller", "") or (entry.get("extra_data", {}) or {}).get("controller", "")
            raw_date = entry.get("date_added")
            dt = parse_datetime(raw_date) if raw_date else None

            # Человеческие строки даты/времени, как в QRR
            date_str_fmt = dt.strftime("%d.%m.%Y") if dt else ""
            time_str_fmt = localtime(dt).strftime("%H:%M") if (dt and is_aware(dt)) else (dt.strftime("%H:%M") if dt else "")

            line = entry.get("line", "")
            duration = entry.get("inspection_duration_seconds", "")

            defects = entry.get("defects") or []
            for df in defects:
                did = df.get("id")
                if did not in ids_set:
                    continue

                # Нормализуем грейд, как на QRR-странице
                grade_raw = df.get("grade", "")
                grade_norm = (str(grade_raw) or "").strip().upper()

                # Поля extra и ответственные
                extra = df.get("extra", {}) or {}
                resp_ids = extra.get("qrr_responsibles_ids") or []
                resp_names = extra.get("qrr_responsibles") or []
                if not isinstance(resp_ids, list):
                    resp_ids = [resp_ids] if resp_ids else []
                if not isinstance(resp_names, list):
                    resp_names = [resp_names] if resp_names else []

                # Дата/время назначения ответственных
                qrr_set_by = extra.get("qrr_set_by") or ""
                qrr_set_at = extra.get("qrr_set_at") or ""
                qrr_responsible_fio = extra.get("qrr_responsible_fio") or ""

                # Карточка в формате, совместимом с QRR UI
                name = df.get("name") or df.get("defect_description", "Без описания")
                unit = df.get("unit", "")
                comment = df.get("comment", "")
                photos = df.get("photos", []) or []

                card = {
                    # базовые для таблицы
                    "date": dt,
                    "date_str": date_str_fmt,
                    "time_str": time_str_fmt,
                    "controller": controller,
                    "defect_description": name,
                    "photos": photos,
                    "photos_json": json.dumps(photos),
                    "has_defect": True,
                    "group_key": f"{vin}_{raw_date}",
                    "unit": unit,
                    "grade": grade_norm,
                    "comment": comment,
                    "line": line,
                    "duration": duration,
                    # доп. для UI
                    "vin": vin,
                    "zone": post_name,          # в history это «зона/пост»
                    "post": post_name,          # как на QRR (человеческое имя поста)
                    "entry_id": entry_id,
                    "defect_id": did,
                    "extra": extra,
                    "date_added": raw_date,
                    "controller_raw": controller,
                    "qrr_responsibles_ids": resp_ids,
                    "qrr_responsibles": resp_names,
                    "qrr_set_by": qrr_set_by,
                    "qrr_set_at": qrr_set_at,
                    "qrr_responsible_fio": qrr_responsible_fio,
                }
                results.append(card)
    return results


def get_defect_details(vin: str, defect_id: str) -> dict | None:
    """Обратная совместимость: вернуть один дефект по ID.
    Если найдено несколько (теоретически), отдаём первый.
    """
    rows = get_defect_details_many(vin, [defect_id])
    return rows[0] if rows else None



