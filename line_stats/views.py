from __future__ import annotations
from datetime import date as date_cls, datetime, timedelta, time as time_cls
from typing import List, Tuple
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from users.decorators import role_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.timezone import get_current_timezone, make_aware, is_aware, now as tz_now
from django.utils.dateparse import parse_date
from django.contrib.auth.decorators import permission_required
# --- Разбор даты из строки в нескольких форматах ---
from datetime import datetime as _dt



def _parse_any_date(s: str | None):
    if not s:
        return None
    # сначала стандарт Django (YYYY-MM-DD)
    d = parse_date(s)
    if d:
        return d
    # затем популярный формат DD.MM.YYYY
    try:
        return _dt.strptime(s, "%d.%m.%Y").date()
    except Exception:
        pass
    # затем ISO с временем
    try:
        return _dt.fromisoformat(s).date()
    except Exception:
        pass
    return None

from .models import (
    FINAL_POSTS,
    EditorsWhitelist,
    HourlyLineStat,
    HourlyPlan,
    HourlyPDIStat,
    SHIFT_CHOICES,
    SHIFTS,
    get_slots,
)
from .forms import (
    DailyParamsForm,
    PlanEditorForm,
    PDIDailyParamsForm,
    make_reason_formset,
)

PROD_LINES = ["gwm", "frame", "chery", "changan"]

# --- Вспомогательные функции ---

def _to_time(s: str) -> time_cls:
    h, m = map(int, s.split(":"))
    return time_cls(h, m)


def _slot_bounds(prod_date: date_cls, s: str, e: str) -> Tuple[datetime, datetime]:
    """Вернём aware-датавремена для начала/конца слота.
    Учитываем переход через полночь.
    """
    tz = get_current_timezone()
    t0, t1 = _to_time(s), _to_time(e)
    d0 = datetime.combine(prod_date, t0)
    d1 = datetime.combine(prod_date, t1)
    if t1 < t0:  # конец на следующий день
        d1 += timedelta(days=1)
    return make_aware(d0, tz), make_aware(d1, tz)

def _slot_duration_minutes(s_label: str, e_label: str) -> int:
    """Длительность окна в минутах (по отображаемому времени, без буфера)."""
    t0, t1 = _to_time(s_label), _to_time(e_label)
    base = datetime.combine(date_cls(2000, 1, 1), t0)
    end = datetime.combine(date_cls(2000, 1, 1), t1)
    if t1 < t0:
        end += timedelta(days=1)
    return int((end - base).total_seconds() // 60)


def _match_bounds_with_buffer(prod_date: date_cls, s_label: str, e_label: str, shift: str | None = None) -> Tuple[datetime, datetime]:
    """
    Границы слота для подсчёта ФАКТА с буфером +5 мин к окончанию,
    и +5 мин к началу для всех слотов, кроме того, что стартует в 07:30.
    Для второй смены (s2) слоты, начинающиеся после полуночи, считаются на prod_date + 1 день,
    но относятся к prod_date.
    """
    tz = get_current_timezone()
    # Смещение буфера
    # Стартовый буфер +5 применяем для всех КРОМЕ самого первого слота 07:30
    # и слотов, которые начинаются сразу после перерывов (без сдвига старта):
    # 09:40, 12:50, 14:40, 18:40, 21:00, 23:10
    after_break_starts = {"09:40", "12:50", "14:40", "18:40", "21:00", "23:10"}
    if s_label == "07:30" or s_label in after_break_starts:
        shift_start_buf = 0
    else:
        shift_start_buf = 0
    # Всегда держим +5 к окончанию слота
    shift_end_buf = 0

    t0 = _to_time(s_label)
    t1 = _to_time(e_label)

    # Базовая дата для начала слота (логика производственного дня):
    # для второй смены слоты, которые фактически после полуночи, считаем на следующий календарный день,
    # но они относятся к той же производственной дате prod_date.
    base_date_start = prod_date
    if (shift or "").lower() == "s2" and t0 < _to_time("16:30"):
        base_date_start = prod_date + timedelta(days=1)

    d0 = datetime.combine(base_date_start, t0) + timedelta(minutes=shift_start_buf)

    # Конец слота относительно той же базовой даты; если время конца < начала — перенос на следующий день
    d1_base_date = base_date_start
    if t1 < t0:
        d1_base_date = base_date_start + timedelta(days=1)
    d1 = datetime.combine(d1_base_date, t1) + timedelta(minutes=shift_end_buf)

    return make_aware(d0, tz), make_aware(d1, tz)

# --- Слот-статус helper ---
def _slot_status(prod_date: date_cls, s_label: str, e_label: str, current_dt: datetime, shift: str) -> str:
    """Вернёт 'future' | 'current' | 'past' относительно ТЕКУЩЕГО времени
    с учётом буферных границ слота (смещения +5 минут) и смены."""
    start_dt, end_dt = _match_bounds_with_buffer(prod_date, s_label, e_label, shift)
    if current_dt < start_dt:
        return "future"
    if start_dt <= current_dt < end_dt:
        return "current"
    return "past"

# --- Правила редактирования причин простоя ---
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

def _edit_deadline(prod_date: date_cls, shift: str) -> datetime:
    """Крайнее время редактирования причин для заданной производственной даты/смены.
    s1 → до 21:00 того же дня; s2 → до 09:00 следующего календарного дня.
    Возвращает aware datetime в текущей TZ.
    """
    tz = get_current_timezone()
    shift = (shift or "s1").lower()
    if shift == "s2":
        d = prod_date + timedelta(days=1)
        dt = datetime.combine(d, time_cls(9, 0))
    else:
        dt = datetime.combine(prod_date, time_cls(21, 0))
    return make_aware(dt, tz)



SECTION_CHIEF_GROUPS = {"section_chiefs", "line_chiefs", "Начальники участков", "Начальник участка", "head_area"}

def _user_in_editors(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True

    # 1) модельная привилегия
    try:
        if user.has_perm("line_stats.change_hourlylinestat"):
            return True
    except Exception:
        pass

    # 1.5) прямая роль в кастомной модели пользователя
    try:
        role_val = getattr(user, "role", None)
        if isinstance(role_val, str) and role_val.lower().replace(" ", "") in {"head_area", "headarea"}:
            return True
    except Exception:
        pass

    # 2) группа начальников участка / head_area
    try:
        user_groups = set(user.groups.values_list("name", flat=True))
        if SECTION_CHIEF_GROUPS.intersection(user_groups):
            return True
    except Exception:
        pass

    # 3) белый список
    try:
        wl = EditorsWhitelist.objects.first()
        if wl and wl.users.filter(pk=user.pk).exists():
            return True
    except Exception:
        pass

    return False

# --- Права на редактирование ПЛАНА: только из EditorsWhitelist (плюс суперпользователь) ---
def _user_can_edit_plans(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    try:
        wl = EditorsWhitelist.objects.first()
        return bool(wl and wl.users.filter(pk=user.pk).exists())
    except Exception:
        return False


def _can_edit_now(user, prod_date: date_cls, shift: str, now_dt: datetime) -> bool:
    return _user_in_editors(user) and now_dt <= _edit_deadline(prod_date, shift)


# === Расчёт ФАКТА по посту "Финал текущий контроль" ===
# Примечание: берём из VINHistory (как обсуждали ранее) по зонам/постам Final.
try:
    from vehicle_history.models import VINHistory
except Exception:  # на случай отсутствия импорта в раннюю фазу
    VINHistory = None  # type: ignore


def _norm(s: str) -> str:
    return (s or "").strip().lower()

# допускаем разные написания финального поста
_FINAL_NORMALIZED = { _norm(x) for x in FINAL_POSTS }

def _is_final_post(name: str) -> bool:
    n = _norm(name)
    if n in _FINAL_NORMALIZED:
        return True
    # запасной эвристический вариант: содержит "финал" и "контрол"
    return ("финал" in n and "контрол" in n) or ("final" in n and ("qc" in n or "control" in n))


def _iter_final_entries(vh) -> List[dict]:
    hist = getattr(vh, "history", None)
    if not hist:
        return []
    # Если хранится как JSON-строка — распарсим
    if isinstance(hist, str):
        try:
            hist = json.loads(hist)
        except Exception:
            return []
    if not isinstance(hist, dict):
        return []

    # Найдём раздел "Цех сборки" без учёта регистра
    zone_dict = None
    for k, v in hist.items():
        if _norm(k) == _norm("Цех сборки"):
            zone_dict = v
            break
    if not isinstance(zone_dict, dict):
        return []

    out: List[dict] = []
    for post_name, entries in zone_dict.items():
        if _is_final_post(post_name):
            if isinstance(entries, list):
                out.extend(entries)
    return out

# --- PDI (УУД) helpers ---
def _iter_uud_entries(vh) -> List[dict]:
    """Достаём события УУД: зона "УУД" → пост "УУД" (как в твоём JSON)."""
    hist = getattr(vh, "history", None)
    if not hist:
        return []
    if isinstance(hist, str):
        try:
            hist = json.loads(hist)
        except Exception:
            return []
    if not isinstance(hist, dict):
        return []

    zone_dict = None
    for k, v in hist.items():
        if _norm(k) == _norm("УУД"):
            zone_dict = v
            break
    if not isinstance(zone_dict, dict):
        return []

    out: List[dict] = []
    for post_name, entries in zone_dict.items():
        if _norm(post_name) == _norm("УУД") and isinstance(entries, list):
            out.extend(entries)
    return out

def collect_pdi_counts(prod_date: date_cls, slots: list[tuple[str, str]], shift: str):
    """Возвращает список длиной len(slots) со словарями {in, out, wip} для PDI (УУД).
    Логика:
      - in: есть время шага 1 (step1_at) и оно попадает в слот (с буфером);
      - out: есть время шага 4 (step4_at) и оно попадает в слот (с буфером);
      - wip: машина находится на шаге 2 и ещё не дошла до шага 3 на протяжении слота
             (step2_at <= конец слота; и (step3_at отсутствует или > начало слота)).
    """
    bounds = [_match_bounds_with_buffer(prod_date, s, e, shift) for (s, e) in slots]
    res = [{"in": 0, "out": 0, "wip": 0} for _ in slots]

    if VINHistory is None:
        return res

    qs = VINHistory.objects.exclude(history__isnull=True).only("history")
    for vh in qs.iterator():
        for e in _iter_uud_entries(vh):
            ed = e.get("extra_data") or {}
            step1 = _parse_dt_str(ed.get("step1_at"))
            step2 = _parse_dt_str(ed.get("step2_at"))
            step3 = _parse_dt_str(ed.get("step3_at"))
            step4 = _parse_dt_str(ed.get("step4_at"))

            # in/out — точечные попадания
            if step1 is not None:
                for i, (b0, b1) in enumerate(bounds):
                    if b0 <= step1 < b1:
                        res[i]["in"] += 1
                        break
            if step4 is not None:
                for i, (b0, b1) in enumerate(bounds):
                    if b0 <= step4 < b1:
                        res[i]["out"] += 1
                        break

            # wip — считаем только те машины, которые на шаге 2 И не имеют шага 3 и шага 4
            if step2 is not None and step3 is None and step4 is None:
                for i, (b0, b1) in enumerate(bounds):
                    # активна в любом слоте, который наступил после начала step2
                    if step2 <= b1:
                        res[i]["wip"] += 1
    return res


def _parse_dt_str(dt_s: str):
    """Parse ISO datetime string that may be naive or timezone-aware.
    Returns an aware datetime in current timezone, or None on failure.
    """
    if not dt_s:
        return None
    try:
        dt = datetime.fromisoformat(dt_s)
    except Exception:
        return None
    tz = get_current_timezone()
    if is_aware(dt):
        return dt.astimezone(tz)
    return make_aware(dt, tz)


def _extract_vin(entry: dict, vh=None) -> str:
    """Извлекаем VIN из записи поста или из самой модели VINHistory.
    Возвращаем пустую строку, если VIN определить не удалось."""
    if not isinstance(entry, dict):
        entry = {}
    # Популярные варианты ключей
    for k in ("vin", "VIN", "vin_number", "vinNumber", "Vin", "vinNumberRaw"):
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # Фолбэк: из объекта VINHistory (если там есть поле vin/vin_number)
    try:
        if vh is not None:
            for attr in ("vin", "vin_number", "vinNumber"):
                v = getattr(vh, attr, None)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    except Exception:
        pass
    return ""

def collect_actual_counts(prod_date: date_cls, slots: list[tuple[str, str]], shift: str):
    """Собираем фактические проходы за день по всем линиям и слотам за один проход по БД.
    Возвращает dict: { line: [cnt_per_slot...] } длиной len(slots) для каждой линии.
    Теперь учитываются только уникальные VIN-ы в каждом слоте.
    """
    # подготовим границы слотов
    slot_bounds = [_match_bounds_with_buffer(prod_date, s, e, shift) for (s, e) in slots]
    # Накапливаем множества VIN-ов по каждому слоту, затем возьмём размер множества
    line_slot_vins = {ln: [set() for _ in range(len(slots))] for ln in PROD_LINES}

    if VINHistory is None:
        # возвращаем нули
        return {ln: [0]*len(slots) for ln in PROD_LINES}

    qs = VINHistory.objects.exclude(history__isnull=True).only("history")
    for vh in qs.iterator():
        for entry in _iter_final_entries(vh):
            dt_s = (
                entry.get("date")
                or entry.get("saved_at")
                or entry.get("datetime")
                or entry.get("date_added")
            )
            dt = _parse_dt_str(dt_s)
            if dt is None:
                continue
            line = _norm(entry.get("line"))
            if line not in line_slot_vins:
                # игнорим чужие/неизвестные линии
                continue
            vin = _extract_vin(entry, vh)
            if not vin:
                # без VIN не учитываем в уникальном подсчёте
                continue
            # найдём индекс слота (их немного — линейный поиск дешевле и нагляднее)
            for idx, (b0, b1) in enumerate(slot_bounds):
                if b0 <= dt < b1:
                    line_slot_vins[line][idx].add(vin)
                    break
    # Преобразуем множества VIN-ов в счётчики
    result = {ln: [len(vset) for vset in arr] for ln, arr in line_slot_vins.items()}
    return result


def calc_actual_for_slot(prod_date: date_cls, line: str, shift: str, s: str, e: str) -> int:
    """Сколько уникальных машин (по VIN) прошло финал в данном часовом слоте."""
    if VINHistory is None:
        return 0
    start_dt, end_dt = _match_bounds_with_buffer(prod_date, s, e, shift)
    line_lc = (line or "").lower()
    seen_vins = set()
    for vh in VINHistory.objects.exclude(history__isnull=True).only("history").iterator():
        for entry in _iter_final_entries(vh):
            dt_s = (
                entry.get("date")
                or entry.get("saved_at")
                or entry.get("datetime")
                or entry.get("date_added")
            )
            dt = _parse_dt_str(dt_s)
            if dt is None:
                continue
            if not (start_dt <= dt < end_dt):
                continue
            ev_line = (entry.get("line") or "").lower()
            if ev_line != line_lc:
                continue
            vin = _extract_vin(entry, vh)
            if vin:
                seen_vins.add(vin)
    return len(seen_vins)


def calc_downtime_minutes(plan: int, actual: int, slot_start: str, slot_end: str) -> int:
    """Грубая модель простоя через недовыпуск.
    Если фактическое меньше плана, считаем долю недовыпуска * длительность слота (в мин).
    """
    if plan <= 0:
        return 0
    t0, t1 = _to_time(slot_start), _to_time(slot_end)
    dur = (datetime.combine(date_cls(2000, 1, 1), t1) - datetime.combine(date_cls(2000, 1, 1), t0)).total_seconds()
    if t1 < t0:
        dur += 24 * 3600  # через полночь
    minutes = int(round(max(0.0, (plan - actual) / float(plan)) * (dur / 60.0)))
    return minutes


def build_rows_for_line(prod_date: date_cls, line: str, shift: str, slots: list[tuple[str, str]], actual_by_slot: list[int]):
    rows = []
    totals = {"plan": 0, "actual": 0, "down": 0}
    for i, (s_label, e_label) in enumerate(slots):
        s, e = _to_time(s_label), _to_time(e_label)
        plan = HourlyPlan.resolve_for(date=prod_date, line=line, start=s, end=e, shift=shift)
        actual = actual_by_slot[i]
        downtime = calc_downtime_minutes(plan, actual, s_label, e_label)
        obj = HourlyLineStat.objects.filter(date=prod_date, line=line, shift=shift, start=s, end=e).first()
        reason = obj.downtime_reason if obj else ""
        author = (
            getattr(obj.reason_author, "get_full_name", lambda: getattr(obj.reason_author, "username", ""))()
            if obj and obj.reason_author else ""
        )
        rows.append({
            "slot": f"{s_label}-{e_label}",
            "plan": plan,
            "actual": actual,
            "down": downtime,
            "reason": reason,
            "author": author,
        })
        totals["plan"] += plan
        totals["actual"] += actual
        totals["down"] += downtime
    return rows, totals


# === ВИД: Таблица дня по линии/смене (план/факт/простой/причина) ===
@login_required
@permission_required('users.access_to_indicators', raise_exception=True)
def offtake_table_view(request: HttpRequest) -> HttpResponse:
    # POST: сохраняем причины простоя для конкретной линии (только текст и автора)
    if request.method == "POST":
        prod_date = _parse_any_date(request.POST.get("date")) or date_cls.today()
        shift = (request.POST.get("shift") or "s1").lower()
        line = (request.POST.get("line") or "").lower()

        if line not in PROD_LINES:
            messages.error(request, "Неизвестная линия.")
            return redirect(f"{request.path}?date={prod_date}&shift={shift}")

        # Проверка права редактирования по whitelist/ролям и дедлайну
        if not _can_edit_now(request.user, prod_date, shift, tz_now()):
            messages.error(request, "Редактирование для выбранной даты/смены закрыто.")
            return redirect(f"{request.path}?date={prod_date}&shift={shift}")

        total_forms = int(request.POST.get("form-TOTAL_FORMS", 0))
        saved = 0
        for i in range(total_forms):
            s_label = request.POST.get(f"form-{i}-start")
            e_label = request.POST.get(f"form-{i}-end")
            if not s_label or not e_label:
                continue
            reason = (request.POST.get(f"form-{i}-downtime_reason") or "").strip()

            # Разрешаем сохранять только для ЗАКРЫТЫХ слотов
            status = _slot_status(prod_date, s_label, e_label, tz_now(), shift)
            if status != "past":
                continue

            try:
                s_t = _to_time(s_label)
                e_t = _to_time(e_label)
            except Exception:
                continue

            obj = HourlyLineStat.objects.filter(date=prod_date, line=line, shift=shift, start=s_t, end=e_t).first()
            if obj is None:
                # Создаём снапшот для закрытого слота (фиксируем факт/простой один раз)
                plan_snap = HourlyPlan.resolve_for(date=prod_date, line=line, start=s_t, end=e_t, shift=shift)
                actual_val = calc_actual_for_slot(prod_date, line, shift, s_label, e_label)
                down_val = calc_downtime_minutes(plan_snap, actual_val, s_label, e_label)
                obj = HourlyLineStat.objects.create(
                    date=prod_date, line=line, shift=shift, start=s_t, end=e_t,
                    plan_snapshot=plan_snap, actual=actual_val, downtime_min=down_val,
                    created_by=request.user if request.user.is_authenticated else None,
                )

            current_reason = obj.downtime_reason or ""
            if reason == current_reason:
                continue

            if reason == "":
                obj.downtime_reason = ""
                obj.reason_author = None
            else:
                obj.downtime_reason = reason
                obj.reason_author = request.user if request.user.is_authenticated else None
            obj.save(update_fields=["downtime_reason", "reason_author"])
            saved += 1

        if saved:
            messages.success(request, f"Сохранено причин: {saved}.")
        else:
            messages.info(request, "Изменений не было.")

        return redirect(f"{request.path}?date={prod_date}&shift={shift}")

    # GET: общая таблица для всех линий + PDI
    raw_date = request.GET.get("date")
    raw_shift = request.GET.get("shift")
    prod_date = _parse_any_date(raw_date) or date_cls.today()
    shift = (raw_shift or "s1").lower()

    # Форма только для отображения полей (не влияет на расчёты)
    base_form = DailyParamsForm(initial={
        "date": prod_date,
        "shift": shift,
    })

    slots = list(get_slots(shift))
    # Текущее время (aware) для определения статуса слота
    now_dt = tz_now()

    can_edit = _can_edit_now(request.user, prod_date, shift, now_dt)
    edit_deadline = _edit_deadline(prod_date, shift)

    # Считаем факт единым проходом по БД для всех линий и слотов
    actual_map = collect_actual_counts(prod_date, slots, shift)

    # Сборка по 4 линиям с автоснапшотом закрытых слотов
    lines_data = {}
    formsets = {}
    for line in PROD_LINES:
        rows = []
        sum_plan = sum_actual = sum_down = 0
        for i, (s_label, e_label) in enumerate(slots):
            s, e = _to_time(s_label), _to_time(e_label)
            plan = HourlyPlan.resolve_for(date=prod_date, line=line, start=s, end=e, shift=shift)
            status = _slot_status(prod_date, s_label, e_label, now_dt, shift)

            actual = 0
            downtime = 0
            reason = ""
            author = ""

            if status == "past":
                # закрытый слот — читаем из снапшота либо фиксируем один раз
                snap = HourlyLineStat.objects.filter(date=prod_date, line=line, shift=shift, start=s, end=e).first()
                if snap is None:
                    actual = actual_map.get(line, [0]*len(slots))[i]
                    downtime = calc_downtime_minutes(plan, actual, s_label, e_label)
                    snap = HourlyLineStat.objects.create(
                        date=prod_date, line=line, shift=shift, start=s, end=e,
                        plan_snapshot=plan, actual=actual, downtime_min=downtime,
                        created_by=request.user if request.user.is_authenticated else None,
                    )
                # берём из снапшота
                plan = snap.plan_snapshot or plan
                actual = snap.actual
                downtime = snap.downtime_min
                if snap.downtime_reason:
                    reason = snap.downtime_reason
                if snap.reason_author:
                    try:
                        author = snap.reason_author.get_full_name() or snap.reason_author.username
                    except Exception:
                        author = ""

            elif status == "current":
                # текущий слот — считаем онлайн, но не записываем
                actual = actual_map.get(line, [0]*len(slots))[i]
                downtime = calc_downtime_minutes(plan, actual, s_label, e_label)
                # если причину уже сохраняли — покажем
                snap = HourlyLineStat.objects.filter(date=prod_date, line=line, shift=shift, start=s, end=e).first()
                if snap:
                    if snap.downtime_reason:
                        reason = snap.downtime_reason
                    if snap.reason_author:
                        try:
                            author = snap.reason_author.get_full_name() or snap.reason_author.username
                        except Exception:
                            author = ""

            else:  # future
                # будущие слоты — только план, 0/0; но причину/автора покажем, если заранее внесены
                snap = HourlyLineStat.objects.filter(date=prod_date, line=line, shift=shift, start=s, end=e).first()
                if snap:
                    if snap.downtime_reason:
                        reason = snap.downtime_reason
                    if snap.reason_author:
                        try:
                            author = snap.reason_author.get_full_name() or snap.reason_author.username
                        except Exception:
                            author = ""

            rows.append({
                "slot": f"{s_label}-{e_label}",
                "plan": plan,
                "actual": actual,
                "down": downtime,
                "reason": reason,
                "author": author,
            })
            sum_plan += plan
            sum_actual += actual
            sum_down += downtime

        lines_data[line] = {"rows": rows, "totals": {"plan": sum_plan, "actual": sum_actual, "down": sum_down}}
        FS = make_reason_formset(slots, user=request.user)
        formsets[line] = FS()

    # PDI (УУД) с автоснапшотом закрытых слотов
    pdi_live = collect_pdi_counts(prod_date, slots, shift)
    pdi_rows = []
    total_in = total_out = total_wip = 0
    for i, (s_label, e_label) in enumerate(slots):
        s, e = _to_time(s_label), _to_time(e_label)
        status = _slot_status(prod_date, s_label, e_label, now_dt, shift)
        inc = outc = wip = 0
        if status == "past":
            snap = HourlyPDIStat.objects.filter(date=prod_date, shift=shift, start=s, end=e).first()
            if snap is None:
                live = pdi_live[i]
                snap = HourlyPDIStat.objects.create(
                    date=prod_date, shift=shift, start=s, end=e,
                    in_count=live["in"], out_count=live["out"], wip_count=live["wip"],
                    created_by=request.user if request.user.is_authenticated else None,
                )
            inc, outc, wip = snap.in_count, snap.out_count, snap.wip_count
        elif status == "current":
            live = pdi_live[i]
            inc, outc, wip = live["in"], live["out"], live["wip"]
        else:  # future
            inc = outc = wip = 0

        pdi_rows.append({"slot": f"{s_label}-{e_label}", "in": inc, "out": outc, "wip": wip})
        total_in += inc
        total_out += outc
        total_wip += wip

    pdi = {"rows": pdi_rows, "totals": {"in": total_in, "out": total_out, "wip": total_wip}}

    # Композитные строки для шаблона, чтобы избежать индексирования по ключам в шаблоне
    compound_rows = []
    for i, (s_label, e_label) in enumerate(slots):
        by_line_list = [lines_data[line]["rows"][i] for line in PROD_LINES]
        p_slot = pdi_rows[i]
        mins = _slot_duration_minutes(s_label, e_label)
        status = _slot_status(prod_date, s_label, e_label, now_dt, shift)
        compound_rows.append({
            "slot": f"{s_label}-{e_label} ({mins}\u00A0мин)",
            "by_line_list": by_line_list,
            "pdi": p_slot,
            "status": status,
        })

    # Итоги в виде списка (в порядке PROD_LINES), чтобы не индексировать словарь из шаблона
    totals_list = [lines_data[line]["totals"] for line in PROD_LINES]

    ctx = {
        "form": base_form,
        "slots": slots,
        "lines": PROD_LINES,
        "lines_data": lines_data,
        "formsets": formsets,
        "pdi": pdi,
        "compound_rows": compound_rows,
        "totals_list": totals_list,
        "can_edit": can_edit,
        "edit_deadline": edit_deadline,
        "prod_date": prod_date,
        "shift": shift,
        "can_edit_plans": _user_can_edit_plans(request.user),
    }
    return render(request, "line_stats/offtake_table.html", ctx)


# === ВИД: PDI (вошло/вышло/в ремонте) ===
# (legacy: отдельная PDI-страница не используется)
@login_required
@permission_required('users.access_to_indicators', raise_exception=True)
def pdi_table_view(request: HttpRequest) -> HttpResponse:
    initial = {
        "date": request.GET.get("date") or date_cls.today().isoformat(),
        "shift": request.GET.get("shift") or "s1",
    }
    form = PDIDailyParamsForm(initial)
    if not form.is_valid():
        return render(request, "line_stats/pdi_table.html", {"form": form, "rows": []})

    prod_date = parse_date(str(form.cleaned_data["date"])) or date_cls.today()
    shift = form.cleaned_data["shift"]

    slots = list(get_slots(shift))
    rows = []
    total_in = total_out = total_wip = 0

    for s_label, e_label in slots:
        s, e = _to_time(s_label), _to_time(e_label)
        obj = HourlyPDIStat.objects.filter(date=prod_date, shift=shift, start=s, end=e).first()
        if obj:
            inc, outc, wip = obj.in_count, obj.out_count, obj.wip_count
        else:
            inc = outc = wip = 0
        rows.append((f"{s_label}-{e_label}", inc, outc, wip))
        total_in += inc
        total_out += outc
        total_wip += wip

    ctx = {
        "form": form,
        "rows": rows,
        "totals": {"in": total_in, "out": total_out, "wip": total_wip},
        "can_edit_plans": _user_can_edit_plans(request.user),
    }
    return render(request, "line_stats/pdi_table.html", ctx)



# === ВИД: Редактор планов (админ‑стиль — единая таблица) ===
@login_required
@permission_required('users.access_to_indicators', raise_exception=True)
def plan_editor_view(request: HttpRequest) -> HttpResponse:
    """Админ‑подобный bulk‑редактор: одна таблица со всеми строками.
    Меняем только поле value. Все значения сохраняются одной кнопкой.
    Дата "effective_from" общая — сверху.
    Доступ: только суперпользователь или из EditorsWhitelist.
    """
    if not _user_can_edit_plans(request.user):
        messages.error(request, "Нет прав на редактирование планов (доступ только из списка EditorsWhitelist).")
        return redirect("line_stats:offtake")

    # Параметр даты действия
    eff_raw = request.POST.get("effective_from") if request.method == "POST" else request.GET.get("effective_from")
    eff_date = _parse_any_date(eff_raw) or tz_now().date()

    # Удобные структуры
    LINES4 = [("changan", "CHANGAN"), ("chery", "CHERY"), ("frame", "GWM FRAME LINE"), ("gwm", "GWM")]
    s1_slots = list(SHIFTS["s1"])  # [("07:30","08:30"), ...]
    s2_slots = list(SHIFTS["s2"])  # [("16:30","17:30"), ...]

    def _nm(line_key: str, shift_key: str, s_label: str, e_label: str) -> str:
        return f"value_{line_key}_{shift_key}_{s_label.replace(':','')}_{e_label.replace(':','')}"

    def _to_time_local(s: str) -> time_cls:
        h, m = s.split(":"); return time_cls(int(h), int(m))

    # Сохранение — обрабатываем ВСЕ поля за раз
    if request.method == "POST":
        changed = 0
        for line_key, _ in LINES4:
            for shift_key, slots in (("s1", s1_slots), ("s2", s2_slots)):
                for s_label, e_label in slots:
                    name = _nm(line_key, shift_key, s_label, e_label)
                    raw = request.POST.get(name)
                    if raw is None or raw == "":
                        continue
                    try:
                        val = int(raw)
                        if val < 0:
                            continue
                    except Exception:
                        continue

                    obj, created = HourlyPlan.objects.get_or_create(
                        line=line_key,
                        shift=shift_key,
                        start=_to_time_local(s_label),
                        end=_to_time_local(e_label),
                        effective_from=eff_date,
                        defaults={"value": val, "created_by": request.user},
                    )
                    if created:
                        changed += 1
                    else:
                        if obj.value != val:
                            obj.value = val
                            if not obj.created_by_id:
                                obj.created_by = request.user
                            obj.save(update_fields=["value", "created_by"])  # аккуратнее
                            changed += 1
        if changed:
            messages.success(request, f"Сохранено изменений: {changed} слотов.")
        else:
            messages.info(request, "Изменений не обнаружено.")
        # Остаёмся на той же дате
        return redirect(f"{request.path}?effective_from={eff_date.isoformat()}")

    # Построение строк таблицы (как в админке)
    rows = []
    for line_key, line_title in LINES4:
        for shift_key, slots in (("s1", s1_slots), ("s2", s2_slots)):
            for s_label, e_label in slots:
                # текущее значение плана по состоянию на eff_date (последняя запись <= eff_date)
                current = (
                    HourlyPlan.objects
                    .filter(line=line_key, shift=shift_key,
                            start=_to_time_local(s_label), end=_to_time_local(e_label),
                            effective_from__lte=eff_date)
                    .order_by("-effective_from", "-created_at")
                    .first()
                )
                rows.append({
                    "line_key": line_key,
                    "line": line_title,
                    "shift": dict(SHIFT_CHOICES).get(shift_key, shift_key),
                    "slot": f"{s_label}-{e_label}",
                    "name": _nm(line_key, shift_key, s_label, e_label),
                    "value": current.value if current else "",
                    "created_by": (current.created_by.get_username() if (current and current.created_by) else ""),
                    "created_at": current.created_at if current else None,
                })

    ctx = {
        "effective_from": eff_date,
        "rows": rows,
    }
    return render(request, "line_stats/plan_editor.html", ctx)

