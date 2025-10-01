from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Set, Tuple

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from vehicle_history.models import VINHistory
from vehicle_history.models import AssemblyPassLog  # adjust import path if your app name differs
from vehicle_history.models import VESPassLog  # VES IN/OUT logs
from supplies.models import TraceData  # бренд/модель по VIN

from django.db.models import Q


# === Настраиваемые константы (при необходимости поправь названия постов) ===
ZONE_ASSEMBLY = "Цех сборки"
# Посты, которые считаем «TRIM OUT» (финал текущий контроль)

FINAL_POST_NAMES = [
    "Финал текущий контроль",
    "Финал текущий контроль, DKD",
    "Final Current Control",
]

# Посты, считающиеся «QA IN» (первая инспекция)
QA_POST_NAMES = [
    "Зазоры и перепады",
    "Экстерьер",
    "Интерьер",
    "Багажник",
    "Мотор",
    "Функцонал",
]

# Пост(ы) "Тестовая линия финал" (исключаем из BQA ALL, если VIN там уже был)
TEST_LINE_FINAL_POST_NAMES = [
       "Геометрия колес",
    "Регулировка света фар и калибровка руля",
    "Тормозная система",
    "Underbody",
    "ADAS",
    "AVM",
    "Герметичность кузова",

    "Диагностика",
    "Тест трек",
    "Документация",
]

# Пост(ы) для SIGN OFF
SIGN_OFF_POST_NAMES = [
    "Документация",
]

# UUD (устранение недостатков)
ZONE_UUD = "УУД"
POST_UUD = "УУД"

BRAND_MAP = {
    "gwm": ["haval", "tank"],
    "chery": ["chery"],
    "changan": ["changan"],
}

LINE_FROM_BRAND = {b: "gwm" for b in ("haval", "tank")}
LINE_FROM_BRAND.update({"chery": "chery", "changan": "changan"})

def _infer_line_by_brand(brand: str | None) -> str:
    b = (brand or "").strip().lower()
    return LINE_FROM_BRAND.get(b, "")


@dataclass(frozen=True)
class PostEvent:
    vin: str
    dt: datetime          # aware datetime в TZ проекта

    @property
    def date(self) -> str:
        return timezone.localtime(self.dt).date().isoformat()

    @property
    def time(self) -> str:
        return timezone.localtime(self.dt).strftime("%H:%M")


# === ВСПОМОГАТЕЛЬНОЕ ===

def _to_aware(dt: datetime | None) -> Optional[datetime]:
    """Приводим к aware datetime в текущем TZ, если возможно."""
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _parse_entry_dt(raw: str | None) -> Optional[datetime]:
    """Безопасно парсим date_added из JSON (ISO-строка)."""
    if not raw:
        return None
    try:
        parsed = parse_datetime(raw)
    except Exception:
        parsed = None
    return _to_aware(parsed)


# === TRIM IN ===

def get_trim_in_events(*, start: Optional[datetime] = None, end: Optional[datetime] = None,
                       line: Optional[str] = None) -> List[PostEvent]:
    """
    Возвращает список событий TRIM IN из AssemblyPassLog за период [start, end].
    Возвращаемые события содержат VIN и точное время сканирования.

    Параметры:
      - start/end: границы периода (aware). Если не заданы — берём все.
      - line: фильтр по линии (gwm/chery/changan) — опционально.
    """
    qs = AssemblyPassLog.objects.all()
    if line:
        qs = qs.filter(line=line)
    if start:
        qs = qs.filter(scanned_at__gte=start)
    if end:
        qs = qs.filter(scanned_at__lte=end)

    events: List[PostEvent] = []

    for row in qs.only("vin", "scanned_at"):
        events.append(PostEvent(vin=row.vin, dt=_to_aware(row.scanned_at)))

    # Сортируем по времени для детерминированного вывода
    events.sort(key=lambda e: e.dt)
    return events


# === TRIM OUT ===

from django.utils import timezone as tz
from vehicle_history.models import VINHistory
from supplies.models import TraceData


def _iter_trim_out_events_from_history(
    histories: Optional[Iterable[VINHistory]] = None, *,
    start=None, end=None, brands=None, models=None, vin=None, line=None
):
    """
    Итерирует события TRIM OUT из VINHistory и возвращает PostEvent(vin, dt).
    Совместима с вызовами вида:
        _iter_trim_out_events_from_history(VINHistory.objects.all(), start=..., end=...)
    Если histories не передан — берём все VINHistory.

    Фильтры brand/model/line применяются через TraceData (vin_c и vin_rk поддерживаются).
    Возвращается САМОЕ РАННЕЕ событие TRIM OUT в периоде по каждому VIN.
    """
    # Базовый набор историй
    qs = histories if histories is not None else VINHistory.objects.all().only("vin", "history")

    # Фильтры VIN/бренд/модель/линия — через TraceData
    if vin or brands or models or line:
        tqs = TraceData.objects.all().only("vin_c", "vin_rk", "brand", "model", "line")
        if vin:
            v_up = (vin or "").strip()
            tqs = tqs.filter(Q(vin_c__iexact=v_up) | Q(vin_rk__iexact=v_up))
        if brands:
            tqs = tqs.filter(brand__in=[b.strip() for b in brands])
        if models:
            tqs = tqs.filter(model__in=[m.strip() for m in models])
        if line:
            tqs = tqs.filter(line__iexact=line)

        vin_set = set()
        for v in tqs.values_list("vin_c", flat=True):
            if v:
                vin_set.add(v.upper())
        for v in tqs.values_list("vin_rk", flat=True):
            if v:
                vin_set.add(v.upper())

        if hasattr(qs, "filter"):
            qs = qs.filter(vin__in=list(vin_set)) if vin_set else qs.none()
        else:
            qs = [h for h in qs if (getattr(h, "vin", "") or "").upper() in vin_set]

    # Нормализуем границы периода к aware
    start = start and (start if tz.is_aware(start) else tz.make_aware(start))
    end   = end   and (end   if tz.is_aware(end)   else tz.make_aware(end))

    earliest_by_vin: dict[str, datetime] = {}

    # Обход JSON-истории
    def _walk_times(node):
        if isinstance(node, dict):
            keys_dt = ("date", "date_added", "created_at", "dt")
            for k, val in node.items():
                # ВАЖНО: используем правильную константу со списком финальных постов
                if k in set(FINAL_POST_NAMES) and isinstance(val, (dict, list)):
                    items = val if isinstance(val, list) else [val]
                    for it in items:
                        if not isinstance(it, dict):
                            continue
                        dt_raw = None
                        for kd in keys_dt:
                            if kd in it and it[kd]:
                                dt_raw = it[kd]
                                break
                        if not dt_raw:
                            continue
                        # Приводим к aware datetime
                        dt_obj = None
                        if isinstance(dt_raw, datetime):
                            dt_obj = dt_raw if tz.is_aware(dt_raw) else tz.make_aware(dt_raw)
                        else:
                            # строки / иное — безопасно парсим
                            dt_obj = _parse_entry_dt(dt_raw)
                        if not dt_obj:
                            continue
                        if start and dt_obj < start:
                            continue
                        if end and dt_obj > end:
                            continue
                        yield dt_obj
                # рекурсия внутрь
                yield from _walk_times(val)
        elif isinstance(node, list):
            for el in node:
                yield from _walk_times(el)

    # Основной цикл по историям VIN
    iterator = qs.iterator() if hasattr(qs, "iterator") else qs
    for h in iterator:
        vin_u = (getattr(h, "vin", "") or "").upper()
        if not vin_u:
            continue
        hist = getattr(h, "history", {}) or {}

        best_dt = None
        for dt in _walk_times(hist):
            if (best_dt is None) or (dt < best_dt):
                best_dt = dt

        if best_dt is not None:
            cur = earliest_by_vin.get(vin_u)
            if cur is None or best_dt < cur:
                earliest_by_vin[vin_u] = best_dt

    # Возвращаем PostEvent'ы (как ожидают вызывающие функции)
    for v, dt in sorted(earliest_by_vin.items(), key=lambda kv: kv[1]):
        yield PostEvent(vin=v, dt=dt)


def get_trim_out_count_from_history(**kwargs) -> int:
    return sum(1 for _ in _iter_trim_out_events_from_history(**kwargs))


# === Generic iterator for events by post names (QA IN / SIGN OFF) ===
def _iter_history_events_for_posts(histories: Iterable[VINHistory], post_names: List[str],
                                   *, start: Optional[datetime] = None,
                                   end: Optional[datetime] = None) -> Iterable[PostEvent]:
    """Итерируем события по списку постов из JSON VINHistory."""
    pset = set(post_names or [])
    for vh in histories:
        posts_by_zone = (vh.history or {}).get(ZONE_ASSEMBLY, {})
        for post_name, entries in (posts_by_zone or {}).items():
            if post_name not in pset:
                continue
            for e in entries or []:
                dt = _parse_entry_dt(e.get("date_added") or e.get("date"))
                if not dt:
                    continue
                if start and dt < start:
                    continue
                if end and dt > end:
                    continue
                yield PostEvent(vin=vh.vin, dt=dt)


def get_trim_out_events(*, start: Optional[datetime] = None, end: Optional[datetime] = None) -> List[PostEvent]:
    """Возвращает список событий TRIM OUT за период [start, end] из VINHistory."""
    events = list(_iter_trim_out_events_from_history(VINHistory.objects.all(), start=start, end=end))
    # Если по одному VIN несколько записей — берём самое раннее в рамках периода
    earliest_by_vin: dict[str, PostEvent] = {}
    for ev in events:
        cur = earliest_by_vin.get(ev.vin)
        if cur is None or ev.dt < cur.dt:
            earliest_by_vin[ev.vin] = ev
    return sorted(earliest_by_vin.values(), key=lambda e: e.dt)


# === QA IN / SIGN OFF helpers ===
def get_qa_in_events(*, start: Optional[datetime] = None, end: Optional[datetime] = None) -> List[PostEvent]:
    events = list(_iter_history_events_for_posts(VINHistory.objects.all(), QA_POST_NAMES, start=start, end=end))
    earliest_by_vin: dict[str, PostEvent] = {}
    for ev in events:
        cur = earliest_by_vin.get(ev.vin)
        if cur is None or ev.dt < cur.dt:
            earliest_by_vin[ev.vin] = ev
    return sorted(earliest_by_vin.values(), key=lambda e: e.dt)


def get_sign_off_events(*, start: Optional[datetime] = None, end: Optional[datetime] = None) -> List[PostEvent]:
    events = list(_iter_history_events_for_posts(VINHistory.objects.all(), SIGN_OFF_POST_NAMES, start=start, end=end))
    earliest_by_vin: dict[str, PostEvent] = {}
    for ev in events:
        cur = earliest_by_vin.get(ev.vin)
        if cur is None or ev.dt < cur.dt:
            earliest_by_vin[ev.vin] = ev
    return sorted(earliest_by_vin.values(), key=lambda e: e.dt)


# === VES (IN / WIP / OUT) ===
def get_ves_mes(*,
                start: Optional[datetime] = None,
                end: Optional[datetime] = None,
                brands: Optional[List[str]] = None,
                models: Optional[List[str]] = None,
                vin: Optional[str] = None) -> dict:
    """
    Сводка по VES: VES IN / WIP VES / VES OUT.

    Правила:
    - VES IN считаем по VESPassLog.given_at в периоде.
    - VES OUT — по VESPassLog.received_at (не null) в периоде.
    - WIP VES — VIN-ы, у которых есть передача (given_at) и НЕТ приёма (received_at) на момент `end` (или сейчас).

    Фильтры бренда/модели применяются по VIN через TraceData, аналогично другим агрегаторам.

    Возвращаем:
    {
      "overall": {
        "ves_in":  {"count": N, "items": [...]},
        "wip_ves": {"count": M, "items": [...]},
        "ves_out": {"count": K, "items": [...]},
      },
      "by_line": {}
    }

    Каждый item:
    {vin, in_date, in_time, out_date, out_time, controller_give, controller_receive, brand, model}
    """
    brands_norm = _normalize_brand_filter(brands)

    # --- исходные выборки ---
    qs = VESPassLog.objects.all()

    # VES IN (по периодy given_at)
    qs_in = qs
    if start:
        qs_in = qs_in.filter(given_at__gte=start)
    if end:
        qs_in = qs_in.filter(given_at__lte=end)

    # earliest IN per VIN in period
    in_map: dict[str, dict] = {}
    for row in qs_in.order_by("given_at").values(
        "vin", "given_at", "given_by__username", "given_by__first_name", "given_by__last_name",
        "received_at", "received_by__username", "received_by__first_name", "received_by__last_name",
    ):
        v = (row["vin"] or "").upper()
        if vin and v != vin.strip().upper():
            continue
        if v in in_map:
            continue  # уже есть самое раннее в периоде
        in_map[v] = row

    # VES OUT (по периодy received_at)
    qs_out = qs.filter(received_at__isnull=False)
    if start:
        qs_out = qs_out.filter(received_at__gte=start)
    if end:
        qs_out = qs_out.filter(received_at__lte=end)

    out_map: dict[str, dict] = {}
    for row in qs_out.order_by("received_at").values(
        "vin", "given_at", "given_by__username", "given_by__first_name", "given_by__last_name",
        "received_at", "received_by__username", "received_by__first_name", "received_by__last_name",
    ):
        v = (row["vin"] or "").upper()
        if vin and v != vin.strip().upper():
            continue
        if v in out_map:
            continue
        out_map[v] = row

    # --- фильтры по бренду/модели ---
    candidate_vins = set(in_map.keys()) | set(out_map.keys())
    if vin:
        candidate_vins = {vin.strip().upper()}
    if brands_norm or models:
        keep = _apply_brand_model_filters(candidate_vins, brands_norm=brands_norm, models=models)
        in_map  = {v: in_map[v]  for v in list(in_map.keys())  if v in keep}
        out_map = {v: out_map[v] for v in list(out_map.keys()) if v in keep}

    # Бренд/модель
    tmap = _trace_map_for_vins(candidate_vins if not (brands_norm or models) else set(in_map.keys()) | set(out_map.keys()))

    # Формирование элементов
    def _name(username: str | None, fn: str | None, ln: str | None) -> str:
        username = username or ""
        fn = fn or ""; ln = ln or ""
        disp = (f"{fn} {ln}".strip() or username).strip()
        return disp

    # VES IN items
    ves_in_items: List[dict] = []
    for v, r in sorted(in_map.items(), key=lambda kv: kv[1]["given_at"] or timezone.now()):
        dt_in = _to_aware(r.get("given_at"))
        dt_out = _to_aware(r.get("received_at"))
        ves_in_items.append({
            "vin": v,
            "in_date": timezone.localtime(dt_in).date().isoformat() if dt_in else "",
            "in_time": timezone.localtime(dt_in).strftime("%H:%M") if dt_in else "",
            "out_date": timezone.localtime(dt_out).date().isoformat() if dt_out else "",
            "out_time": timezone.localtime(dt_out).strftime("%H:%M") if dt_out else "",
            "controller_give": (r.get("given_by__username") or ""),
            "controller_receive": (r.get("received_by__username") or ""),
            "brand": tmap.get(v, {}).get("brand", ""),
            "model": tmap.get(v, {}).get("model", ""),
        })

    # VES OUT items
    ves_out_items: List[dict] = []
    for v, r in sorted(out_map.items(), key=lambda kv: kv[1]["received_at"] or timezone.now()):
        dt_in = _to_aware(r.get("given_at"))
        dt_out = _to_aware(r.get("received_at"))
        ves_out_items.append({
            "vin": v,
            "in_date": timezone.localtime(dt_in).date().isoformat() if dt_in else "",
            "in_time": timezone.localtime(dt_in).strftime("%H:%M") if dt_in else "",
            "out_date": timezone.localtime(dt_out).date().isoformat() if dt_out else "",
            "out_time": timezone.localtime(dt_out).strftime("%H:%M") if dt_out else "",
            "controller_give": (r.get("given_by__username") or ""),
            "controller_receive": (r.get("received_by__username") or ""),
            "brand": tmap.get(v, {}).get("brand", ""),
            "model": tmap.get(v, {}).get("model", ""),
        })

    # WIP VES: активные на момент end (или сейчас)
    as_of = _to_aware(end) or timezone.now()
    qs_wip = qs.filter(given_at__lte=as_of).filter(Q(received_at__isnull=True) | Q(received_at__gt=as_of))
    if vin:
        qs_wip = qs_wip.filter(vin=vin.strip().upper())

    # Для VIN с несколькими открытыми/пересекающимися интервалами оставим последний по времени IN
    wip_latest: dict[str, dict] = {}
    for row in qs_wip.order_by("vin", "-given_at").values(
        "vin", "given_at", "given_by__username", "given_by__first_name", "given_by__last_name",
    ):
        v = (row["vin"] or "").upper()
        if v in wip_latest:
            continue
        wip_latest[v] = row

    # Применим фильтр бренда/модели к WIP
    if brands_norm or models:
        keep_wip = _apply_brand_model_filters(set(wip_latest.keys()), brands_norm=brands_norm, models=models)
        wip_latest = {v: wip_latest[v] for v in list(wip_latest.keys()) if v in keep_wip}

    ves_wip_items: List[dict] = []
    for v, r in sorted(wip_latest.items(), key=lambda kv: kv[1]["given_at"] or timezone.now()):
        dt_in = _to_aware(r.get("given_at"))
        ves_wip_items.append({
            "vin": v,
            "in_date": timezone.localtime(dt_in).date().isoformat() if dt_in else "",
            "in_time": timezone.localtime(dt_in).strftime("%H:%M") if dt_in else "",
            "out_date": "",
            "out_time": "",
            "controller_give": (r.get("given_by__username") or ""),
            "controller_receive": "",
            "brand": tmap.get(v, {}).get("brand", ""),
            "model": tmap.get(v, {}).get("model", ""),
        })

    return {
        "overall": {
            "ves_in":  {"count": len(ves_in_items),  "items": ves_in_items},
            "wip_ves": {"count": len(ves_wip_items), "items": ves_wip_items},
            "ves_out": {"count": len(ves_out_items), "items": ves_out_items},
        },
        "by_line": {},
    }


# === WIP TRIM ===

def get_wip_trim(*, as_of: Optional[datetime] = None, line: Optional[str] = None) -> List[PostEvent]:
    """
    Возвращает список VIN, которые ЗАШЛИ на TRIM IN (есть в AssemblyPassLog), но ЕЩЕ НЕ ВЫШЛИ через TRIM OUT
    (нет записи финального поста в VINHistory) на момент as_of.

    Для каждого VIN возвращаем время TRIM IN (scanned_at) как ориентир.

    Параметры:
      - as_of: момент времени «на сейчас». По умолчанию — текущие дата/время.
      - line: фильтр по линии (gwm/chery/changan) — опционально.
    """
    if as_of is None:
        as_of = timezone.now()
    as_of = _to_aware(as_of)

    # Все TRIM IN до as_of
    trim_in_qs = AssemblyPassLog.objects.all()
    if line:
        trim_in_qs = trim_in_qs.filter(line=line)
    trim_in_qs = trim_in_qs.filter(scanned_at__lte=as_of)

    in_by_vin: dict[str, datetime] = {}
    for row in trim_in_qs.only("vin", "scanned_at"):
        dt_in = _to_aware(row.scanned_at)
        # Если по какой-то причине появился дубль — оставим самое раннее
        if row.vin not in in_by_vin or dt_in < in_by_vin[row.vin]:
            in_by_vin[row.vin] = dt_in

    if not in_by_vin:
        return []

    # Все TRIM OUT до as_of
    out_events = _iter_trim_out_events_from_history(
        VINHistory.objects.filter(vin__in=list(in_by_vin.keys())), end=as_of
    )
    out_vins: Set[str] = {e.vin for e in out_events}

    # WIP = IN − OUT
    wip_events: List[PostEvent] = [PostEvent(vin=v, dt=in_by_vin[v]) for v in in_by_vin.keys() if v not in out_vins]
    wip_events.sort(key=lambda e: e.dt)
    return wip_events


# === Удобные «плоские» ответы для шаблонов/JSON ===

def serialize_events(events: Iterable[PostEvent]) -> List[dict]:
    """Преобразует события в словари {vin, date, time} для удобного вывода."""
    payload = []
    for e in events:
        payload.append({
            "vin": e.vin,
            "date": e.date,
            "time": e.time,
        })
    return payload


# === ФИЛЬТРАЦИЯ ПО БРЕНДУ/МОДЕЛИ/ВИН ===

def _normalize_brand_filter(brands: Optional[List[str]]) -> Optional[List[str]]:
    if not brands:
        return None
    out: List[str] = []
    for b in brands:
        key = (b or '').strip().lower()
        out.extend(BRAND_MAP.get(key, [key]))
    # уникализируем
    return sorted({x.lower() for x in out})


def _trace_map_for_vins(vins: Iterable[str]) -> dict:
    """
    Вернуть dict VIN -> {brand, model}.
    Поддерживаем оба варианта хранения VIN в TraceData: vin_c и vin_rk.
    """
    vset = {(v or "").upper() for v in vins if v}
    if not vset:
        return {}

    # вытащим все записи, где vin_c или vin_rk совпадает с любым из наших VIN
    qs = TraceData.objects.filter(Q(vin_c__in=vset) | Q(vin_rk__in=vset)) \
                          .values("vin_c", "vin_rk", "brand", "model")

    mapping: dict[str, dict] = {}
    for row in qs:
        vin_c = (row.get("vin_c") or "").upper()
        vin_rk = (row.get("vin_rk") or "").upper()
        brand = row.get("brand") or ""
        model = row.get("model") or ""

        # Привяжем к тому ключу, который реально есть в нашем наборе vset
        if vin_c and vin_c in vset:
            mapping[vin_c] = {"brand": brand, "model": model}
        if vin_rk and vin_rk in vset:
            mapping[vin_rk] = {"brand": brand, "model": model}

    return mapping


def _apply_brand_model_filters(vins: Iterable[str], *,
                               brands_norm: Optional[List[str]] = None,
                               models: Optional[List[str]] = None) -> Set[str]:
    """Оставляем VIN, подходящие по брендам/моделям согласно TraceData."""
    vset = {(v or '').upper() for v in vins if v}
    if not vset:
        return set()
    if not brands_norm and not models:
        return vset
    tmap = _trace_map_for_vins(vset)
    keep: Set[str] = set()
    models_norm = {m.strip() for m in (models or []) if m and m.strip()}
    for v in vset:
        tm = tmap.get(v)
        if not tm:
            continue
        ok = True
        if brands_norm:
            ok = (tm.get("brand", "").lower() in brands_norm)
        if ok and models_norm:
            ok = (tm.get("model", "") in models_norm)
        if ok:
            keep.add(v)
    return keep


# === АГРЕГАТОР ДЛЯ MES ===
def get_trim_mes(*,
                 start: Optional[datetime] = None,
                 end: Optional[datetime] = None,
                 brands: Optional[List[str]] = None,
                 models: Optional[List[str]] = None,
                 vin: Optional[str] = None,
                 line: Optional[str] = None) -> dict:
    """
    Возвращает сводку по TRIM IN / WIP TRIM / TRIM OUT с учётом фильтров.

    Фильтры:
      - start/end: границы периода для событий (TRIM IN по scanned_at, TRIM OUT по date_added).
      - brands: список верхнеуровневых брендов (gwm/chery/changan); маппятся к TraceData.brand по BRAND_MAP.
      - models: список моделей (точное совпадение с TraceData.model).
      - vin: конкретный VIN (если указан — бренд/модель игнорируются для набора VIN).
      - line: фильтр линии для TRIM IN (gwm/chery/changan).

    Возвращаемая структура:
    {
      "trim_in":  {"count": N, "items": [{vin,date,time,saved_by,controller,controller_login,brand,model}]},
      "wip_trim": {"count": M, "items": [{vin,date,time,saved_by,controller,controller_login,brand,model}]},
      "trim_out": {"count": K, "items": [{vin,date,time,controller,brand,model}]},
    }
    """
    brands_norm = _normalize_brand_filter(brands)

    # --- TRIM IN ---
    tin_events = get_trim_in_events(start=start, end=end, line=line)
    # Применим фильтр по VIN сразу, если задан
    if vin:
        v_up = vin.strip().upper()
        tin_events = [e for e in tin_events if e.vin == v_up]

    # Уникальный VIN -> самое раннее событие в периоде
    earliest_in: dict[str, PostEvent] = {}
    for e in tin_events:
        cur = earliest_in.get(e.vin)
        if cur is None or e.dt < cur.dt:
            earliest_in[e.vin] = e

    # Фильтрация по брендам/моделям (через TraceData)
    keep_in_vins = _apply_brand_model_filters(earliest_in.keys(), brands_norm=brands_norm, models=models) if not vin else set([vin.strip().upper()])
    earliest_in = {v: earliest_in[v] for v in earliest_in.keys() if v in keep_in_vins}

    # Соберём saved_by по TRIM IN
    saved_by_map: dict[str, str] = {}
    line_by_vin_in: dict[str, str] = {}
    if earliest_in:
        qs_in = AssemblyPassLog.objects.filter(vin__in=list(earliest_in.keys()))
        for row in qs_in.values("vin", "saved_by__username", "saved_by__first_name", "saved_by__last_name"):
            name = row.get("saved_by__username") or ""
            fn = row.get("saved_by__first_name") or ""
            ln = row.get("saved_by__last_name") or ""
            disp = (f"{fn} {ln}".strip() or name).strip()
            saved_by_map[(row["vin"] or '').upper()] = disp
        for row in qs_in.values("vin", "line"):
            line_by_vin_in[(row["vin"] or '').upper()] = (row["line"] or "")

    # Бренд/модель
    tmap_in = _trace_map_for_vins(earliest_in.keys())

    # Соберём controller_login и controller для TRIM IN/WIP
    saved_by_login_map: dict[str, str] = {}
    if earliest_in:
        qs_in_login = AssemblyPassLog.objects.filter(vin__in=list(earliest_in.keys()))
        for row in qs_in_login.values("vin", "saved_by__username"):
            saved_by_login_map[(row["vin"] or '').upper()] = row.get("saved_by__username") or ""

    trim_in_items = [
        {
            "vin": v,
            "date": timezone.localtime(ev.dt).date().isoformat(),
            "time": timezone.localtime(ev.dt).strftime("%H:%M"),
            "saved_by": saved_by_map.get(v, ""),
            "controller": saved_by_login_map.get(v, ""),
            "controller_login": saved_by_login_map.get(v, ""),
            "brand": tmap_in.get(v, {}).get("brand", ""),
            "model": tmap_in.get(v, {}).get("model", ""),
            "line": line_by_vin_in.get(v, ""),
        }
        for v, ev in sorted(earliest_in.items(), key=lambda x: x[1].dt)
    ]

    # --- TRIM OUT ---
    tout_events = get_trim_out_events(start=start, end=end)
    if vin:
        v_up = vin.strip().upper()
        tout_events = [e for e in tout_events if e.vin == v_up]

    # Бренд/модель для tout нужен раньше VINHistory обхода
    tmap_out = _trace_map_for_vins([e.vin for e in tout_events])

    # Уникальное самое раннее TRIM OUT по VIN уже обеспечено функцией; доп. фильтрация по брендам/моделям:
    keep_out_vins = _apply_brand_model_filters([e.vin for e in tout_events], brands_norm=brands_norm, models=models) if not vin else set([vin.strip().upper()])
    tout_events = [e for e in tout_events if e.vin in keep_out_vins]

    # Соберём controller из VINHistory (если есть)
    controller_by_vin: dict[str, str] = {}
    line_by_vin_out: dict[str, str] = {}
    earliest_out_dt: dict[str, datetime] = {}
    if tout_events:
        # для минимизации обхода — вытащим только нужные VIN
        vset = {e.vin for e in tout_events}
        for vh in VINHistory.objects.filter(vin__in=list(vset)):
            posts_by_zone = (vh.history or {}).get(ZONE_ASSEMBLY, {})
            for post_name, entries in (posts_by_zone or {}).items():
                if post_name not in FINAL_POST_NAMES:
                    continue
                for e in entries or []:
                    dt = _parse_entry_dt(e.get("date_added") or e.get("date"))
                    if not dt:
                        continue
                    # ищем самое раннее
                    if vh.vin not in controller_by_vin or dt < earliest_out_dt.get(vh.vin, dt):
                        controller_by_vin[vh.vin] = (
                            (e.get("controller")
                             or (e.get("extra_data") or {}).get("controller")
                             or ""),
                            dt,
                        )
                        line_val = (e.get("line") or "").strip()
                        if not line_val:
                            # попробуем по бренду
                            line_val = _infer_line_by_brand(tmap_out.get(vh.vin, {}).get("brand"))
                        line_by_vin_out[vh.vin] = line_val
                        earliest_out_dt[vh.vin] = dt
        # оставим только имя
        controller_by_vin = {k: v[0] for k, v in controller_by_vin.items()}

    trim_out_items = [
        {
            "vin": ev.vin,
            "date": timezone.localtime(ev.dt).date().isoformat(),
            "time": timezone.localtime(ev.dt).strftime("%H:%M"),
            "controller": controller_by_vin.get(ev.vin, ""),
            "brand": tmap_out.get(ev.vin, {}).get("brand", ""),
            "model": tmap_out.get(ev.vin, {}).get("model", ""),
            "line": line_by_vin_out.get(ev.vin, ""),
        }
        for ev in sorted(tout_events, key=lambda x: x.dt)
    ]
    # Если задан фильтр line, оставляем только TRIM OUT по этой линии
    if line:
        trim_out_items = [it for it in trim_out_items if (it.get("line") or "") == line]

    # --- WIP (ALL-TIME): VIN, которые когда-либо зашли на TRIM IN,
    #     но ДО текущего момента не прошли TRIM OUT и не прошли «тестовую линию финал». ---
    as_of = _to_aware(end) or timezone.now()

    # 1) Все TRIM IN за всё время (до as_of), с фильтрами VIN/бренд/модель и линией (для IN — по журналу AssemblyPassLog)
    tin_all = get_trim_in_events(start=None, end=as_of, line=line)
    if vin:
        v_up = vin.strip().upper()
        tin_all = [e for e in tin_all if e.vin == v_up]

    earliest_in_all: dict[str, PostEvent] = {}
    for e in tin_all:
        cur = earliest_in_all.get(e.vin)
        if cur is None or e.dt < cur.dt:
            earliest_in_all[e.vin] = e

    keep_in_all_vins = _apply_brand_model_filters(earliest_in_all.keys(), brands_norm=brands_norm, models=models) if not vin else {vin.strip().upper()}
    earliest_in_all = {v: earliest_in_all[v] for v in earliest_in_all.keys() if v in keep_in_all_vins}

    # saved_by и line для всех-времён
    saved_by_all: dict[str, str] = {}
    line_by_vin_in_all: dict[str, str] = {}
    if earliest_in_all:
        qs_in_all = AssemblyPassLog.objects.filter(vin__in=list(earliest_in_all.keys()))
        for row in qs_in_all.values("vin", "saved_by__username", "saved_by__first_name", "saved_by__last_name"):
            name = row.get("saved_by__username") or ""
            fn = row.get("saved_by__first_name") or ""; ln = row.get("saved_by__last_name") or ""
            disp = (f"{fn} {ln}".strip() or name).strip()
            saved_by_all[(row["vin"] or '').upper()] = disp
        for row in qs_in_all.values("vin", "line"):
            line_by_vin_in_all[(row["vin"] or '').upper()] = (row["line"] or "")

    # Бренд/модель для all-time IN
    tmap_in_all = _trace_map_for_vins(earliest_in_all.keys())

    # 2) Все TRIM OUT до as_of (по VINHistory)
    tout_upto = list(_iter_trim_out_events_from_history(
        VINHistory.objects.filter(vin__in=list(earliest_in_all.keys()) if earliest_in_all else []),
        start=None, end=as_of
    ))
    out_vins_upto: Set[str] = {e.vin for e in tout_upto}

    # 3) Все «тестовая линия финал» до as_of (по VINHistory)
    test_final_upto = list(_iter_history_events_for_posts(
        VINHistory.objects.filter(vin__in=list(earliest_in_all.keys()) if earliest_in_all else []),
        TEST_LINE_FINAL_POST_NAMES,
        start=None, end=as_of
    ))
    test_final_vins_upto: Set[str] = {e.vin for e in test_final_upto}

    # 4) Итоговый набор WIP = IN_all − OUT_upto − TEST_FINAL_upto
    wip_all_vins_keys = [v for v in earliest_in_all.keys() if (v not in out_vins_upto and v not in test_final_vins_upto)]

    all_time_wip_items = [
        {
            "vin": v,
            "date": timezone.localtime(ev.dt).date().isoformat(),
            "time": timezone.localtime(ev.dt).strftime("%H:%M"),
            "saved_by": saved_by_all.get(v, ""),
            "controller": saved_by_all.get(v, ""),  # логин/имя как есть, чтобы не плодить поля
            "controller_login": saved_by_all.get(v, ""),
            "brand": tmap_in_all.get(v, {}).get("brand", ""),
            "model": tmap_in_all.get(v, {}).get("model", ""),
            "line": line_by_vin_in_all.get(v, ""),
        }
        for v, ev in sorted(((vk, earliest_in_all[vk]) for vk in wip_all_vins_keys), key=lambda x: x[1].dt)
    ]

    def _by_line(items: list[dict]) -> dict:
        acc = {"gwm": [], "chery": [], "changan": []}
        for it in items:
            ln = (it.get("line") or "").strip()
            if ln in acc:
                acc[ln].append(it)
        return {k: {"count": len(v), "items": v} for k, v in acc.items()}

    by_line = {
        "trim_in": _by_line(trim_in_items),
        "wip_trim": _by_line(all_time_wip_items),
        "trim_out": _by_line(trim_out_items),
    }

    return {
        "overall": {
            "trim_in": {"count": len(trim_in_items), "items": trim_in_items},
            "wip_trim": {"count": len(all_time_wip_items), "items": all_time_wip_items},
            "trim_out": {"count": len(trim_out_items), "items": trim_out_items},
        },
        "by_line": by_line,
    }




# === QA MES AGGREGATOR ===
def get_qa_mes(*,
               start: Optional[datetime] = None,
               end: Optional[datetime] = None,
               brands: Optional[List[str]] = None,
               models: Optional[List[str]] = None,
               vin: Optional[str] = None,
               line: Optional[str] = None) -> dict:
    """
    Сводка по линии QA: QA IN / WIP QA / SIGN OFF.
    Логика аналогична get_trim_mes, но оба источника приходят из VINHistory.
    Возвращаемая структура идентична: overall/by_line и элементы с полями
    {vin,date,time,controller,brand,model,line} (для QA IN и SIGN OFF).
    """
    brands_norm = _normalize_brand_filter(brands)

    # --- 1) QA START (all up to 'end'): take earliest QA IN per VIN with dt <= end ---
    qa_in_events_all = get_qa_in_events(start=None, end=end)
    if vin:
        v_up = vin.strip().upper()
        qa_in_events_all = [e for e in qa_in_events_all if e.vin == v_up]

    keep_qa_all_vins = _apply_brand_model_filters([e.vin for e in qa_in_events_all], brands_norm=brands_norm, models=models) if not vin else {vin.strip().upper()}
    qa_in_events_all = [e for e in qa_in_events_all if e.vin in keep_qa_all_vins]

    # Соберём controller и line для ВСЕХ VIN, что когда-либо заходили в QA до 'end'
    controller_by_vin_in_all: dict[str, str] = {}
    line_by_vin_in_all: dict[str, str] = {}
    if qa_in_events_all:
        vset_all = {e.vin for e in qa_in_events_all}
        tmap_in_all = _trace_map_for_vins(vset_all)
        for vh in VINHistory.objects.filter(vin__in=list(vset_all)):
            posts_by_zone = (vh.history or {}).get(ZONE_ASSEMBLY, {})
            for post_name, entries in (posts_by_zone or {}).items():
                if post_name not in set(QA_POST_NAMES):
                    continue
                for e in entries or []:
                    dt = _parse_entry_dt(e.get("date_added") or e.get("date"))
                    if not dt or dt > (_to_aware(end) or timezone.now()):
                        continue
                    cur = controller_by_vin_in_all.get(vh.vin)
                    if (vh.vin not in line_by_vin_in_all) or (isinstance(cur, tuple) and dt < cur[1]):
                        controller_by_vin_in_all[vh.vin] = (
                            (e.get("controller") or (e.get("extra_data") or {}).get("controller") or ""), dt
                        )
                        ln = (e.get("line") or "").strip()
                        if not ln:
                            ln = _infer_line_by_brand(tmap_in_all.get(vh.vin, {}).get("brand"))
                        line_by_vin_in_all[vh.vin] = ln
        controller_by_vin_in_all = {k: v[0] for k, v in controller_by_vin_in_all.items()}

    tmap_in_full_all = _trace_map_for_vins([e.vin for e in qa_in_events_all])

    # --- 2) QA IN (only in the selected period) ---
    qa_in_events_period = get_qa_in_events(start=start, end=end)
    if vin:
        v_up = vin.strip().upper()
        qa_in_events_period = [e for e in qa_in_events_period if e.vin == v_up]
    keep_qa_period_vins = _apply_brand_model_filters([e.vin for e in qa_in_events_period], brands_norm=brands_norm, models=models) if not vin else {vin.strip().upper()}
    qa_in_events_period = [e for e in qa_in_events_period if e.vin in keep_qa_period_vins]

    tmap_in_full_period = _trace_map_for_vins([e.vin for e in qa_in_events_period])
    qa_in_items = [
        {
            "vin": ev.vin,
            "date": timezone.localtime(ev.dt).date().isoformat(),
            "time": timezone.localtime(ev.dt).strftime("%H:%M"),
            "controller": controller_by_vin_in_all.get(ev.vin, ""),
            "brand": tmap_in_full_period.get(ev.vin, {}).get("brand", ""),
            "model": tmap_in_full_period.get(ev.vin, {}).get("model", ""),
            "line": line_by_vin_in_all.get(ev.vin, ""),
        }
        for ev in sorted(qa_in_events_period, key=lambda x: x.dt)
    ]
    if line:
        qa_in_items = [it for it in qa_in_items if (it.get("line") or "") == line]

    # --- 3) SIGN OFF ---
    # 3a) Для метрики за период
    sign_events_period = get_sign_off_events(start=start, end=end)
    if vin:
        v_up = vin.strip().upper()
        sign_events_period = [e for e in sign_events_period if e.vin == v_up]
    keep_sign_period_vins = _apply_brand_model_filters([e.vin for e in sign_events_period], brands_norm=brands_norm, models=models) if not vin else {vin.strip().upper()}
    sign_events_period = [e for e in sign_events_period if e.vin in keep_sign_period_vins]

    controller_by_vin_sign_period: dict[str, str] = {}
    line_by_vin_sign_period: dict[str, str] = {}
    if sign_events_period:
        vset_p = {e.vin for e in sign_events_period}
        tmap_sign_p = _trace_map_for_vins(vset_p)
        for vh in VINHistory.objects.filter(vin__in=list(vset_p)):
            posts_by_zone = (vh.history or {}).get(ZONE_ASSEMBLY, {})
            for post_name, entries in (posts_by_zone or {}).items():
                if post_name not in set(SIGN_OFF_POST_NAMES):
                    continue
                for e in entries or []:
                    dt = _parse_entry_dt(e.get("date_added") or e.get("date"))
                    if not dt or dt < (_to_aware(start) if start else datetime.min.replace(tzinfo=timezone.get_current_timezone())) or dt > (_to_aware(end) or timezone.now()):
                        continue
                    cur = controller_by_vin_sign_period.get(vh.vin)
                    if (vh.vin not in line_by_vin_sign_period) or (isinstance(cur, tuple) and dt < cur[1]):
                        controller_by_vin_sign_period[vh.vin] = (
                            (e.get("controller") or (e.get("extra_data") or {}).get("controller") or ""), dt
                        )
                        ln = (e.get("line") or "").strip()
                        if not ln:
                            ln = _infer_line_by_brand(tmap_sign_p.get(vh.vin, {}).get("brand"))
                        line_by_vin_sign_period[vh.vin] = ln
        controller_by_vin_sign_period = {k: v[0] for k, v in controller_by_vin_sign_period.items()}

    tmap_sign_full_period = _trace_map_for_vins([e.vin for e in sign_events_period])
    sign_off_items = [
        {
            "vin": ev.vin,
            "date": timezone.localtime(ev.dt).date().isoformat(),
            "time": timezone.localtime(ev.dt).strftime("%H:%M"),
            "controller": controller_by_vin_sign_period.get(ev.vin, ""),
            "brand": tmap_sign_full_period.get(ev.vin, {}).get("brand", ""),
            "model": tmap_sign_full_period.get(ev.vin, {}).get("model", ""),
            "line": line_by_vin_sign_period.get(ev.vin, ""),
        }
        for ev in sorted(sign_events_period, key=lambda x: x.dt)
    ]
    if line:
        sign_off_items = [it for it in sign_off_items if (it.get("line") or "") == line]

    # --- STR: среди машин, прошедших Документацию в выбранном периоде ---
    # Деноминатор: все VIN, прошедшие SIGN OFF ("Документация") в периоде и с учётом фильтров.
    # Числитель: из них VIN БЕЗ единой записи в УУД (когда-либо).

    # Берём VIN именно из уже сформированных sign_off_items (они прошли все фильтры, включая line)
    sign_vins_period_set: set[str] = {it.get("vin", "").upper() for it in (sign_off_items or []) if it.get("vin")}
    str_denominator = len(sign_vins_period_set)

    vins_with_uud: set[str] = set()
    if sign_vins_period_set:
        for vh in VINHistory.objects.filter(vin__in=list(sign_vins_period_set)):
            uud_entries = ((vh.history or {}).get(ZONE_UUD, {}) or {}).get(POST_UUD, []) or []
            if uud_entries:
                vins_with_uud.add(vh.vin)

    str_numerator = max(str_denominator - len(vins_with_uud), 0)
    str_percent = (str_numerator / str_denominator * 100.0) if str_denominator else 0.0

    # 3b) Для расчёта WIP: любые SIGN OFF с dt <= end
    sign_events_upto_end = get_sign_off_events(start=None, end=end)
    if vin:
        v_up = vin.strip().upper()
        sign_events_upto_end = [e for e in sign_events_upto_end if e.vin == v_up]
    keep_sign_upto_vins = _apply_brand_model_filters([e.vin for e in sign_events_upto_end], brands_norm=brands_norm, models=models) if not vin else {vin.strip().upper()}
    sign_vins_upto_end = {e.vin for e in sign_events_upto_end if e.vin in keep_sign_upto_vins}

    # --- 4) WIP QA as of 'end' = (QA started up to end) − (signed off up to end) ---
    wip_candidate_vins = {e.vin for e in qa_in_events_all} - set(sign_vins_upto_end)

    # Исключаем VIN на VES (отданы, но не приняты) на момент 'end'
    as_of = _to_aware(end) or timezone.now()
    if wip_candidate_vins:
        qs_ves_open = VESPassLog.objects.filter(
            vin__in=list(wip_candidate_vins),
            given_at__lte=as_of,
        ).filter(Q(received_at__isnull=True) | Q(received_at__gt=as_of))
        ves_open_vins = {(r["vin"] or "").upper() for r in qs_ves_open.values("vin")}
        if ves_open_vins and (brands_norm or models):
            ves_open_vins = _apply_brand_model_filters(ves_open_vins, brands_norm=brands_norm, models=models)
        wip_candidate_vins = wip_candidate_vins - set(ves_open_vins)

    # Исключаем VIN, которые сейчас находятся на УУД (in/wip/out buffers)
    try:
        uud = get_uud_mes(start=start, end=end, brands=brands, models=models, vin=vin)
        overall_uud = (uud or {}).get("overall", {}) or {}
        groups_to_exclude = ("uud_in_wip_all", "wip_uud", "uud_out_wip")
        uud_vins: set[str] = set()
        for g in groups_to_exclude:
            items = (overall_uud.get(g, {}) or {}).get("items", []) or []
            for it in items:
                v = (it or {}).get("vin")
                if v:
                    uud_vins.add(v)
        if uud_vins:
            wip_candidate_vins = {v for v in wip_candidate_vins if v not in uud_vins}
    except Exception:
        pass

    # Сформируем wip_items из полноты (qa_in_events_all)
    tmap_for_wip = _trace_map_for_vins(wip_candidate_vins)
    wip_items = []
    # Для даты/времени берём dt из qa_in_events_all (их earliest up to end)
    earliest_map = {e.vin: e.dt for e in qa_in_events_all}
    for v in sorted(wip_candidate_vins):
        dt = earliest_map.get(v)
        wip_items.append({
            "vin": v,
            "date": timezone.localtime(dt).date().isoformat() if dt else "",
            "time": timezone.localtime(dt).strftime("%H:%M") if dt else "",
            "controller": controller_by_vin_in_all.get(v, ""),
            "brand": tmap_for_wip.get(v, {}).get("brand", ""),
            "model": tmap_for_wip.get(v, {}).get("model", ""),
            "line": line_by_vin_in_all.get(v, ""),
        })

    if line:
        wip_items = [it for it in wip_items if (it.get("line") or "") == line]

    # --- DPU за ВЫБРАННЫЙ ПЕРИОД [start, end] с фильтрами (как в QRQC) ---
    # Числитель: количество дефектов за период [start, end] по всем постам зоны сборки
    #             ограничено по грейдам: V1+, V2, V3.
    # Знаменатель: количество УНИКАЛЬНЫХ машин за этот же период:
    #              ТОЛЬКО VIN из VINHistory ∈ [start, end].

    # Нормализация и набор допустимых грейдов (исправлено: V1+, V2, V3)
    ALLOWED_GRADES = {"V1+", "V1", "V2"}
    def _norm_grade(g: Optional[str]) -> str:
        if not g:
            return ""
        g2 = (str(g) or "").strip().upper()
        # частые варианты записи
        if g2 in {"V1PLUS", "V1 PLUS", "V1＋", "V1＋ ", "V1 ПЛЮС"}:
            return "V1+"
        return g2

    def _is_in_period(dt: Optional[datetime], s: Optional[datetime], e: Optional[datetime]) -> bool:
        if not dt:
            return False
        if s and dt < s:
            return False
        if e and dt > e:
            return False
        return True

    def _count_entry_defects_in_period(entry: dict, s: Optional[datetime], e: Optional[datetime]) -> int:
        """Считает дефекты только нужных грейдов, попадающие по дате в [s, e].
        Не используем флаг has_defect — считаем только элементы списка defects.
        """
        defs = entry.get("defects")
        if not defs:
            defs = (entry.get("extra_data") or {}).get("defects")
        if not isinstance(defs, list):
            return 0
        cnt = 0
        for d in defs:
            try:
                # поддержка как вложенного dt у дефекта, так и общей даты записи
                d_dt_raw = (d.get("date_added") or d.get("date") or entry.get("date_added") or entry.get("date"))
                d_dt = _parse_entry_dt(d_dt_raw)
                if not _is_in_period(d_dt, s, e):
                    continue
                gr = _norm_grade(d.get("grade"))
                if gr in ALLOWED_GRADES:
                    cnt += 1
            except Exception:
                continue
        return cnt

    # Границы периода (aware)
    start_aw = _to_aware(start) if start else None
    end_aw = _to_aware(end) or timezone.now()

    # --- Числитель: дефекты нужных грейдов за период ---
    dpu_numerator = 0

    # Кеш TraceData для фильтров бренда/модели и определения линии при её отсутствии
    tmap_cache: dict[str, dict] = {}
    def _brand_model_ok(v: str) -> bool:
        vu = (v or '').upper()
        if vin and vu != vin.strip().upper():
            return False
        if not brands_norm and not models:
            return True
        nonlocal tmap_cache
        if vu not in tmap_cache:
            tmap_cache.update(_trace_map_for_vins([vu]))
        tm = tmap_cache.get(vu)
        if not tm:
            return False
        ok = True
        if brands_norm:
            ok = (tm.get("brand", "").lower() in brands_norm)
        if ok and models:
            ok = (tm.get("model", "") in set(models))
        return ok

    for vh in VINHistory.objects.all():
        v = (vh.vin or '').upper()
        if not _brand_model_ok(v):
            continue
        posts_by_zone = (vh.history or {}).get(ZONE_ASSEMBLY, {})
        for post_name, entries in (posts_by_zone or {}).items():
            for e in entries or []:
                # фильтр по линии
                if line:
                    ln = (e.get("line") or "").strip()
                    if not ln:
                        if v not in tmap_cache:
                            tmap_cache.update(_trace_map_for_vins([v]))
                        ln = _infer_line_by_brand((tmap_cache.get(v) or {}).get("brand"))
                    if (ln or "") != line:
                        continue
                dpu_numerator += _count_entry_defects_in_period(e, start_aw, end_aw)

    # --- Знаменатель: уникальные VIN за период (ТОЛЬКО VINHistory) ---
    denom_vins: set[str] = set()

    # VIN из VINHistory (любые посты зоны сборки) с датой записи в периоде
    for vh in VINHistory.objects.all():
        v = (vh.vin or '').upper()
        if not _brand_model_ok(v):
            continue
        posts_by_zone = (vh.history or {}).get(ZONE_ASSEMBLY, {})
        for post_name, entries in (posts_by_zone or {}).items():
            for e in entries or []:
                dt = _parse_entry_dt(e.get("date_added") or e.get("date"))
                if not _is_in_period(dt, start_aw, end_aw):
                    continue
                if line:
                    ln = (e.get("line") or "").strip()
                    if not ln:
                        if v not in tmap_cache:
                            tmap_cache.update(_trace_map_for_vins([v]))
                        ln = _infer_line_by_brand((tmap_cache.get(v) or {}).get("brand"))
                    if (ln or "") != line:
                        continue
                denom_vins.add(v)

    dpu_denominator = len(denom_vins)
    dpu_value = (dpu_numerator / dpu_denominator) if dpu_denominator else 0.0

    # Для QA по-прежнему не возвращаем by_line (одна логическая линия).
    return {
        "overall": {
            "qa_in": {"count": len(qa_in_items), "items": qa_in_items},
            "wip_qa": {"count": len(wip_items), "items": wip_items},
            "sign_off": {"count": len(sign_off_items), "items": sign_off_items},
            # STR: процент и сырьевые значения для прозрачности
            "str": {
                "percent": round(str_percent, 1),
                "numerator": str_numerator,           # прошли SIGN OFF и вообще без записей УУД
                "denominator": str_denominator        # все прошедшие SIGN OFF (в периоде)
            },
            "dpu": {
                "value": round(dpu_value, 3),
                "defects": dpu_numerator,
                "unique_cars_today": dpu_denominator
            },
        },
        "by_line": {},
    }




# === PRE-QA BUFFER (BQA): TRIM OUT → (buffer) → QA IN ===
def get_bqa_mes(*,
                start: Optional[datetime] = None,
                end: Optional[datetime] = None,
                brands: Optional[List[str]] = None,
                models: Optional[List[str]] = None,
                vin: Optional[str] = None,
                line: Optional[str] = None) -> dict:
    """
    BQA (Буфер ожидания QA):
    - bqa_in:      уникальные VIN, у которых есть TRIM OUT в [start, end] (первое попадание в период)
    - bqa_wip_all: VIN с TRIM OUT (последний ≤ end), которые до `end` ещё НЕ проходили другие посты:
                   ни первую инспекцию (QA IN), ни «Тестовая линия финал», ни SIGN OFF.
    - bqa_wip_today: VIN из bqa_wip_all, у которых TRIM OUT ∈ [start, end].

    Фильтры брендов/моделей применяем через TraceData (как в остальных агрегаторах).
    line — опционально, фильтруем по линии TRIM OUT.
    Возвращаем structure как у других: overall/by_line (пустой, т.к. это одна очередь).
    """
    brands_norm = _normalize_brand_filter(brands)
    end = _to_aware(end) or timezone.now()
    # Если период не дан, считаем с начала времён
    start = _to_aware(start) if start else None

    # 1) Собираем TRIM OUT события
    #   - all_up_to_end: для WIP берём ПОСЛЕДНЕЕ TRIM OUT ≤ end
    #   - in_period: для IN берём ПЕРВОЕ TRIM OUT ∈ [start, end]
    all_vh = VINHistory.objects.all()

    latest_trim_out: dict[str, dict] = {}   # vin -> {dt, controller, line}
    earliest_trim_out_in_period: dict[str, dict] = {}  # vin -> {dt, controller, line}

    for vh in all_vh:
        posts_by_zone = (vh.history or {}).get(ZONE_ASSEMBLY, {})
        for post_name, entries in (posts_by_zone or {}).items():
            if post_name not in FINAL_POST_NAMES:
                continue
            for e in entries or []:
                dt = _parse_entry_dt(e.get("date_added") or e.get("date"))
                if not dt:
                    continue

                # latest <= end
                if dt <= end:
                    rec = latest_trim_out.get(vh.vin)
                    if rec is None or dt > rec["dt"]:
                        ln = (e.get("line") or "").strip()
                        latest_trim_out[vh.vin] = {
                            "dt": dt,
                            "controller": (e.get("controller") or (e.get("extra_data") or {}).get("controller") or ""),
                            "line": ln or _infer_line_by_brand((_trace_map_for_vins([vh.vin]).get(vh.vin, {}) or {}).get("brand")),
                        }

                # earliest in [start, end]
                if (start is None or dt >= start) and dt <= end:
                    rec = earliest_trim_out_in_period.get(vh.vin)
                    if rec is None or dt < rec["dt"]:
                        ln = (e.get("line") or "").strip()
                        earliest_trim_out_in_period[vh.vin] = {
                            "dt": dt,
                            "controller": (e.get("controller") or (e.get("extra_data") or {}).get("controller") or ""),
                            "line": ln or _infer_line_by_brand((_trace_map_for_vins([vh.vin]).get(vh.vin, {}) or {}).get("brand")),
                        }

    # 2) Собираем QA IN (для сравнения последнего времени до end)
    latest_qa_in: dict[str, datetime] = {}
    for vh in VINHistory.objects.filter(vin__in=list(latest_trim_out.keys()) if latest_trim_out else []):
        posts_by_zone = (vh.history or {}).get(ZONE_ASSEMBLY, {})
        for post_name, entries in (posts_by_zone or {}).items():
            if post_name not in set(QA_POST_NAMES):
                continue
            for e in entries or []:
                dt = _parse_entry_dt(e.get("date_added") or e.get("date"))
                if not dt or dt > end:
                    continue
                cur = latest_qa_in.get(vh.vin)
                if cur is None or dt > cur:
                    latest_qa_in[vh.vin] = dt

    # 3) Применим фильтры VIN по брендам/моделям
    candidate_vins = set(latest_trim_out.keys()) | set(earliest_trim_out_in_period.keys())
    if vin:
        candidate_vins = {vin.strip().upper()}
    if brands_norm or models:
        keep = _apply_brand_model_filters(candidate_vins, brands_norm=brands_norm, models=models)
        latest_trim_out = {v: latest_trim_out[v] for v in list(latest_trim_out.keys()) if v in keep}
        earliest_trim_out_in_period = {v: earliest_trim_out_in_period[v] for v in list(earliest_trim_out_in_period.keys()) if v in keep}
        latest_qa_in = {v: t for v, t in latest_qa_in.items() if v in keep}

    # 3b) Соберём VIN-ы, которые до end уже прошли «Тестовая линия финал» и SIGN OFF
    # Ограничим поиск нашими кандидатами для эффективности
    candidate_after_filters = set(latest_trim_out.keys()) | set(earliest_trim_out_in_period.keys())
    if not candidate_after_filters and vin:
        candidate_after_filters = {vin.strip().upper()}

    # Test Line Final (до end)
    test_final_events = list(_iter_history_events_for_posts(
        VINHistory.objects.filter(vin__in=list(candidate_after_filters)),
        TEST_LINE_FINAL_POST_NAMES,
        start=None, end=end
    ))
    test_final_vins = {e.vin for e in test_final_events}

    # SIGN OFF (до end)
    sign_off_events_upto_end = get_sign_off_events(start=None, end=end)
    sign_vins_upto_end = {e.vin for e in sign_off_events_upto_end if e.vin in candidate_after_filters}

    # Применим фильтры брендов/моделей к этим наборам тоже (для согласованности)
    if brands_norm or models:
        keep_ext = _apply_brand_model_filters(candidate_after_filters, brands_norm=brands_norm, models=models)
        test_final_vins = {v for v in test_final_vins if v in keep_ext}
        sign_vins_upto_end = {v for v in sign_vins_upto_end if v in keep_ext}

    # 3c) VIN'ы, которые на момент end находятся на УУД (любая стадия: IN buffer / WIP UUD / OUT buffer)
    uud_vins: set[str] = set()
    try:
        uud = get_uud_mes(start=start, end=end, brands=brands, models=models, vin=vin)
        overall_uud = (uud or {}).get("overall", {}) or {}
        for g in ("uud_in_wip_all", "wip_uud", "uud_out_wip"):
            items = (overall_uud.get(g, {}) or {}).get("items", []) or []
            for it in items:
                v = (it or {}).get("vin")
                if v:
                    uud_vins.add(v)
        # Наборы из get_uud_mes уже прошли фильтры brand/model, но оставим на месте для согласованности,
        # если наверху менялась логика фильтрации:
        if brands_norm or models:
            keep_uud = _apply_brand_model_filters(uud_vins, brands_norm=brands_norm, models=models)
            uud_vins = {v for v in uud_vins if v in keep_uud}
    except Exception:
        # Если УУД расчёт недоступен — не исключаем по УУД
        uud_vins = set()

    # 4) Бренд/модель для карточек
    tmap = _trace_map_for_vins(set(latest_trim_out.keys()) | set(earliest_trim_out_in_period.keys()))

    # 5) BQA IN (TRIM OUT в периоде)
    bqa_in_items: List[dict] = []
    for v, rec in sorted(earliest_trim_out_in_period.items(), key=lambda kv: kv[1]["dt"]) if earliest_trim_out_in_period else []:
        ln = rec.get("line") or _infer_line_by_brand(tmap.get(v, {}).get("brand"))
        if line and (ln or "") != line:
            continue
        dt = rec["dt"]
        bqa_in_items.append({
            "vin": v,
            "trim_out_date": timezone.localtime(dt).date().isoformat(),
            "trim_out_time": timezone.localtime(dt).strftime("%H:%M"),
            "controller_out": rec.get("controller", ""),
            "brand": tmap.get(v, {}).get("brand", ""),
            "model": tmap.get(v, {}).get("model", ""),
            "line": ln,
        })

    # 6) WIP ALL (строго): VIN с TRIM OUT (последний ≤ end),
    #    которые ДО end НЕ проходили QA IN, Test Line Final и SIGN OFF
    bqa_wip_all_items: List[dict] = []
    qa_in_vins_upto_end = set(latest_qa_in.keys())
    exclude_vins = qa_in_vins_upto_end | set(test_final_vins) | set(sign_vins_upto_end) | set(uud_vins)

    for v, rec in latest_trim_out.items():
        if v in exclude_vins:
            continue
        ln = rec.get("line") or _infer_line_by_brand(tmap.get(v, {}).get("brand"))
        if line and (ln or "") != line:
            continue
        t_out = rec["dt"]
        bqa_wip_all_items.append({
            "vin": v,
            "trim_out_date": timezone.localtime(t_out).date().isoformat(),
            "trim_out_time": timezone.localtime(t_out).strftime("%H:%M"),
            "controller_out": rec.get("controller", ""),
            "brand": tmap.get(v, {}).get("brand", ""),
            "model": tmap.get(v, {}).get("model", ""),
            "line": ln,
        })
    # Отсортируем по времени TRIM OUT (descending, свежие VIN видны первыми)
    bqa_wip_all_items.sort(key=lambda it: (it.get("trim_out_date"), it.get("trim_out_time")), reverse=True)

    # 7) WIP TODAY: те же VIN, но с TRIM OUT в периоде
    in_vins_today = {it["vin"] for it in bqa_in_items}
    bqa_wip_today_items = [it for it in bqa_wip_all_items if it["vin"] in in_vins_today]

    return {
        "overall": {
            "bqa_in": {"count": len(bqa_in_items), "items": bqa_in_items},
            "bqa_wip_today": {"count": len(bqa_wip_today_items), "items": bqa_wip_today_items},
            "bqa_wip_all": {"count": len(bqa_wip_all_items), "items": bqa_wip_all_items},
        },
        "by_line": {},
    }


# === UUD MES AGGREGATOR ===
def get_uud_mes(*,
                start: Optional[datetime] = None,
                end: Optional[datetime] = None,
                brands: Optional[List[str]] = None,
                models: Optional[List[str]] = None,
                vin: Optional[str] = None) -> dict:
    """
    Сводка по участку УУД по шагам 1–4 (хранятся в VINHistory["УУД"]["УУД"][...].extra_data):
      1) step1_at/by — QA отдал на УУД (ещё не приняли) → UUD IN
      2) step2_at/by — УУД принял (ремонт идёт) → WIP UUD (+1), исключается из UUD IN буфера
      3) step3_at/by — УУД закончил и отдал QA (QA ещё не принял) → UUD OUT (period), UUD OUT buffer (+1)
      4) step4_at/by — QA принял обратно → UUD OUT buffer −1

    Возвращаем:
      - uud_in:           уникальные VIN со step1 ∈ [start, end] (первое попадание в период)
      - uud_in_wip_today: VIN со step1 ∈ [start, end] и НЕТ step2 ≤ end (стоят до приёма, только «сегодняшние»)
      - uud_in_wip_all:   VIN со step1 ≤ end и НЕТ step2 ≤ end (весь хвост на конец периода)
      - wip_uud:          VIN со step2 ≤ end и НЕТ step3 ≤ end (в ремонте сейчас)
      - uud_out:          уникальные VIN со step3 ∈ [start, end] (первое попадание в период)
      - uud_out_wip:      VIN со step3 ≤ end и НЕТ step4 ≤ end (отданы QA, но ещё не приняты)

    Фильтры brands/models применяются через TraceData. Линии нет.
    """
    brands_norm = _normalize_brand_filter(brands)
    end = _to_aware(end) or timezone.now()
    start = _to_aware(start) if start else None

    # Соберём по каждому VIN самые поздние (до end) времена step1..step4 и контролёров,
    # а также самые ранние (в периоде) step1/step3 для метрик "за период".
    latest_steps: dict[str, dict] = {}
    earliest_step1: dict[str, dict] = {}
    earliest_step3: dict[str, dict] = {}
    # Первое событие на УУД в периоде (если нет step1, используем step2, иначе step3)
    earliest_enter: dict[str, dict] = {}

    def _upd_earliest(store: dict, vin: str, dt: Optional[datetime], who_key: str, who_val: str):
        if not dt:
            return
        if start and dt < start:
            return
        if dt > end:
            return
        cur = store.get(vin)
        if (cur is None) or (dt < cur["dt"]):
            store[vin] = {"dt": dt, who_key: who_val}

    for vh in VINHistory.objects.all():
        zz = (vh.history or {}).get(ZONE_UUD, {})
        entries = (zz or {}).get(POST_UUD, [])
        if not entries:
            continue
        for e in entries:
            ex = e.get("extra_data") or {}
            s1 = _parse_entry_dt(ex.get("step1_at"))
            s2 = _parse_entry_dt(ex.get("step2_at"))
            s3 = _parse_entry_dt(ex.get("step3_at"))
            s4 = _parse_entry_dt(ex.get("step4_at"))
            by1 = (ex.get("step1_by") or "")
            by2 = (ex.get("step2_by") or "")
            by3 = (ex.get("step3_by") or "")
            by4 = (ex.get("step4_by") or "")

            # накопим latest<=end
            rec = latest_steps.get(vh.vin) or {}
            if s1 and s1 <= end:
                if ("s1" not in rec) or (s1 > rec["s1"]["dt"]):
                    rec["s1"] = {"dt": s1, "by": by1}
            if s2 and s2 <= end:
                if ("s2" not in rec) or (s2 > rec["s2"]["dt"]):
                    rec["s2"] = {"dt": s2, "by": by2}
            if s3 and s3 <= end:
                if ("s3" not in rec) or (s3 > rec["s3"]["dt"]):
                    rec["s3"] = {"dt": s3, "by": by3}
            if s4 and s4 <= end:
                if ("s4" not in rec) or (s4 > rec["s4"]["dt"]):
                    rec["s4"] = {"dt": s4, "by": by4}
            if rec:
                latest_steps[vh.vin] = rec

            # Earliest in-period step1 / step3
            _upd_earliest(earliest_step1, vh.vin, s1, "by", by1)
            _upd_earliest(earliest_step3, vh.vin, s3, "by", by3)
            # Первое событие на УУД в периоде: step1 (предпочтительно), иначе step2, иначе step3
            _upd_earliest(earliest_enter, vh.vin, s1, "by", by1)
            _upd_earliest(earliest_enter, vh.vin, s2, "by", by2)
            _upd_earliest(earliest_enter, vh.vin, s3, "by", by3)

    # Кандидаты VIN для бренд/модель фильтра
    candidate_vins = set(latest_steps.keys()) | set(earliest_step1.keys()) | set(earliest_step3.keys())
    if vin:
        candidate_vins = {vin.strip().upper()}

    if brands_norm or models:
        keep = _apply_brand_model_filters(candidate_vins, brands_norm=brands_norm, models=models)
        latest_steps = {v: latest_steps[v] for v in list(latest_steps.keys()) if v in keep}
        earliest_step1 = {v: earliest_step1[v] for v in list(earliest_step1.keys()) if v in keep}
        earliest_step3 = {v: earliest_step3[v] for v in list(earliest_step3.keys()) if v in keep}
        earliest_enter = {v: earliest_enter[v] for v in list(earliest_enter.keys()) if v in keep}

    tmap = _trace_map_for_vins(set(latest_steps.keys()) | set(earliest_step1.keys()) | set(earliest_step3.keys()) | set(earliest_enter.keys()))

    def _fmt(dt: Optional[datetime]) -> tuple[str, str]:
        if not dt:
            return "", ""
        return timezone.localtime(dt).date().isoformat(), timezone.localtime(dt).strftime("%H:%M")

    # --- UUD IN (строго step1 в выбранном периоде; уникальные VIN) ---
    uud_in_items: List[dict] = []
    if earliest_step1:
        for v, rec in sorted(earliest_step1.items(), key=lambda kv: kv[1]["dt"]):
            d, t = _fmt(rec["dt"])
            uud_in_items.append({
                "vin": v,
                "step1_date": d,
                "step1_time": t,
                "controller_in": rec.get("by", ""),
                "brand": tmap.get(v, {}).get("brand", ""),
                "model": tmap.get(v, {}).get("model", ""),
            })
    # Безопасная уникализация по VIN (на случай дублей записей в JSON)
    _seen_vins = set()
    _unique_uud_in_items = []
    for it in uud_in_items:
        v = (it.get("vin") or "").upper()
        if v and v not in _seen_vins:
            _seen_vins.add(v)
            _unique_uud_in_items.append(it)
    uud_in_items = _unique_uud_in_items

    # --- UUD IN WIP: step1 <= end и НЕТ step2 <= end ---
    uud_in_wip_all_items: List[dict] = []
    for v, rec in latest_steps.items():
        s1 = rec.get("s1", {}).get("dt"); s2 = rec.get("s2", {}).get("dt")
        if s1 and ((s2 is None) or (s1 > s2)):
            d, t = _fmt(s1)
            uud_in_wip_all_items.append({
                "vin": v,
                "step1_date": d,
                "step1_time": t,
                "controller_in": rec.get("s1", {}).get("by", ""),
                "brand": tmap.get(v, {}).get("brand", ""),
                "model": tmap.get(v, {}).get("model", ""),
            })
    # Свежие сверху
    uud_in_wip_all_items.sort(key=lambda it: (it.get("step1_date"), it.get("step1_time")), reverse=True)

    # Сегодняшние стоящие — те же, но ограничим VIN из uud_in_items
    in_today_vins = {it["vin"] for it in uud_in_items}
    uud_in_wip_today_items = [it for it in uud_in_wip_all_items if it["vin"] in in_today_vins]

    # --- WIP UUD: step2 ≤ end и НЕТ step3 ≤ end ---
    wip_uud_items: List[dict] = []
    for v, rec in latest_steps.items():
        s2 = rec.get("s2", {}).get("dt"); s3 = rec.get("s3", {}).get("dt")
        if s2 and ((s3 is None) or (s2 > s3)):
            d, t = _fmt(s2)
            wip_uud_items.append({
                "vin": v,
                "step2_date": d,
                "step2_time": t,
                "controller_work": rec.get("s2", {}).get("by", ""),
                "brand": tmap.get(v, {}).get("brand", ""),
                "model": tmap.get(v, {}).get("model", ""),
            })
    wip_uud_items.sort(key=lambda it: (it.get("step2_date"), it.get("step2_time")), reverse=True)

    # --- UUD OUT (step3 в периоде) ---
    uud_out_items: List[dict] = []
    for v, rec in sorted(earliest_step3.items(), key=lambda kv: kv[1]["dt"]) if earliest_step3 else []:
        d, t = _fmt(rec["dt"])
        uud_out_items.append({
            "vin": v,
            "step3_date": d,
            "step3_time": t,
            "controller_finish": rec.get("by", ""),
            "brand": tmap.get(v, {}).get("brand", ""),
            "model": tmap.get(v, {}).get("model", ""),
        })

    # --- UUD OUT buffer: step3 ≤ end и НЕТ step4 ≤ end ---
    uud_out_wip_items: List[dict] = []
    for v, rec in latest_steps.items():
        s3 = rec.get("s3", {}).get("dt"); s4 = rec.get("s4", {}).get("dt")
        if s3 and ((s4 is None) or (s3 > s4)):
            d, t = _fmt(s3)
            uud_out_wip_items.append({
                "vin": v,
                "step3_date": d,
                "step3_time": t,
                "controller_finish": rec.get("s3", {}).get("by", ""),
                "brand": tmap.get(v, {}).get("brand", ""),
                "model": tmap.get(v, {}).get("model", ""),
            })
    uud_out_wip_items.sort(key=lambda it: (it.get("step3_date"), it.get("step3_time")), reverse=True)

    return {
        "overall": {
            "uud_in": {"count": len(uud_in_items), "items": uud_in_items},
            "uud_in_wip_today": {"count": len(uud_in_wip_today_items), "items": uud_in_wip_today_items},
            "uud_in_wip_all": {"count": len(uud_in_wip_all_items), "items": uud_in_wip_all_items},
            "wip_uud": {"count": len(wip_uud_items), "items": wip_uud_items},
            "uud_out": {"count": len(uud_out_items), "items": uud_out_items},
            "uud_out_wip": {"count": len(uud_out_wip_items), "items": uud_out_wip_items},
        },
        "by_line": {},
    }



