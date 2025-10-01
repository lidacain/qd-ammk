from django.shortcuts import render
from users.decorators import role_required
from django.contrib.auth.decorators import permission_required
#
# --- QRR access helpers ---
QRR_ALLOWED_ROLES = {"qrr_specialist", "qrr_supervisor", "qrr_shift_lead"}
QRR_WHITELIST_USERS = {
    "r.kabdyzhanov",
    "du.konakbayev",
    "s.abdrakhman",
    "a.kukentayev",
    "t.saparbayev",
    "d.zhapargali",
    "y.askarov",
    "a.yelemessov",
    "a.bizhanova",
    "i.gabdualiev",
    "g.kurmanaliev",
    "d.satybaldykyzy",
    'lidacain',
    'lidacain_m',
    'lidacain_qrr',
    't.tokshekenov',
    'miko',
}

def _user_in_groups(user, names):
    try:
        return user.groups.filter(name__in=names).exists()
    except Exception:
        return False

def _user_has_any_role(user, roles):
    # Flexible check: tries common patterns used for role storage
    try:
        if hasattr(user, "role") and isinstance(user.role, str):
            return user.role in roles
        if hasattr(user, "roles") and isinstance(user.roles, (list, tuple, set)):
            return any(r in roles for r in user.roles)
        # fallback to Django Groups
        return _user_in_groups(user, roles)
    except Exception:
        return False

def ensure_qrr_or_whitelist(user):
    return (
        (user and user.is_authenticated) and (
            user.get_username() in QRR_WHITELIST_USERS or _user_has_any_role(user, QRR_ALLOWED_ROLES)
        )
    )
from vehicle_history.models import VINHistory
from django.contrib.auth.decorators import login_required
from datetime import datetime
from .models import QRRInvestigation, QRRResponsible
from .utils import create_qrr_investigation_from_entry
from django.utils.timezone import localtime
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from .forms import QRRInvestigationForm
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json
from collections import defaultdict
from django.utils.dateparse import parse_datetime
from supplies.models import TraceData


# Функция генерации номера формы
def generate_form_number():
    date_part = timezone.now().strftime("%Y-%m")
    last_form = QRRInvestigation.objects.filter(form_number__startswith=date_part).order_by('-form_number').first()
    if last_form:
        last_num = int(last_form.form_number.split('-')[-1])
    else:
        last_num = 0
    return f"{date_part}-{last_num + 1:03d}"


@login_required
@role_required(['qrr_specialist', 'qrr_supervisor', 'qrr_shift_lead'])
def qrr_dashboard(request):
    return render(request, 'qrr/qrr_dashboard.html')


@login_required
def qrr_blank_create(request):
    if request.method == "POST":
        form = QRRInvestigationForm(request.POST, request.FILES)
        if form.is_valid():
            qrr = form.save(commit=False)
            qrr.created_by = request.user
            qrr.form_number = generate_form_number()
            qrr.form_date = timezone.now().date()
            qrr.form_time = timezone.now().time()
            qrr.save()
            form.save_m2m()
            messages.success(request, "✅ Пустой БРД успешно создан.")
            return redirect('qrr_blank_list')  # предполагаем, что есть URL для списка БРД
        else:
            messages.error(request, "❌ Ошибка при создании БРД. Проверьте форму.")
    else:
        form = QRRInvestigationForm()

    return render(request, "qrr/qrr_blank_create.html", {"form": form})


@login_required
@role_required(["qrr_specialist", "qrr_supervisor", "qrr_shift_lead"])
def qrr_blank_list(request):
    grouped = {
        "V1+": [],
        "V1": [],
        "V2": [],
        "V2(Серийный)": [],
        "V3": []
    }

    seen_keys = set()  # ✅ Уникальные ключи VIN + станция + дата

    for vin_history in VINHistory.objects.all():
        vin = vin_history.vin
        history = vin_history.history

        for zone_name, posts in history.items():
            for post_name, entries in posts.items():
                for entry in entries:
                    defects = entry.get("defects", [])
                    if not defects:
                        continue

                    # Фильтруем дефекты по нужным грейдам
                    matching_defects = [d for d in defects if d.get("grade") in grouped]
                    if not matching_defects:
                        continue  # Пропускаем, если нет подходящих дефектов

                    date_str = entry.get("date_added", "")
                    try:
                        date_obj = datetime.fromisoformat(date_str)
                        date_only = date_obj.date()
                    except Exception:
                        continue

                    key = f"{vin}|{zone_name}|{post_name}|{date_only}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    form = QRRInvestigation.objects.filter(
                        vin=vin,
                        station=f"{zone_name} / {post_name}",
                        form_date=date_only
                    ).first()

                    entry_data = {
                        "vin": vin,
                        "post": post_name,
                        "zone": zone_name,
                        "controller": entry.get("controller", ""),
                        "date_added": localtime(date_obj),
                        "defects": matching_defects,
                        "form_number": form.form_number if form else None,
                        "status": form.status if form else "not_created",
                        "created_by": form.created_by.get_full_name_with_patronymic() if form and form.created_by else None,
                        "investigation": form
                    }

                    first_grade = matching_defects[0].get("grade", "")
                    if first_grade == "V2(Серийный)":
                        grouped["V2(Серийный)"].append(entry_data)
                    elif first_grade in grouped:
                        grouped[first_grade].append(entry_data)

    manual_list = QRRInvestigation.objects.filter(vin_history__isnull=True).order_by('-created_at')

    return render(request, "qrr/qrr_blank_list.html", {
        "grouped": grouped,
        "manual_list": manual_list
    })


@login_required
@role_required(["qrr_specialist", "qrr_supervisor", "qrr_shift_lead"])
def create_qrr_blank(request):
    vin = request.GET.get("vin")
    station = request.GET.get("station")
    date_str = request.GET.get("date")

    if not vin or not station or not date_str:
        messages.error(request, "Отсутствуют необходимые параметры.")
        return redirect("qrr_blank_list")

    try:
        form_date = datetime.fromisoformat(date_str).date()
    except Exception:
        messages.error(request, "Неверная дата.")
        return redirect("qrr_blank_list")

    vin_history = get_object_or_404(VINHistory, vin=vin)
    zone, post = station.split(" / ", 1)

    # Ищем нужный entry
    for entry in vin_history.history.get(zone, {}).get(post, []):
        if entry.get("date_added", "").startswith(date_str):
            create_qrr_investigation_from_entry(vin, station, entry, created_by=request.user)
            messages.success(request, f"БРД успешно создан для VIN {vin}.")
            break
    else:
        messages.error(request, "Не удалось найти нужную запись для создания БРД.")

    return redirect("qrr_blank_list")


@login_required
@permission_required('users.access_to_the_qrr_responsible', raise_exception=True)
def qrr_defects_board(request):
    """
    Страница для команды QRR: список всех дефектов цеха сборки (за все время),
    с полной информацией, чтобы назначать ответственных и менять грейды.
    Параметры:
      - grade: V1+, V1, V2, V3, ALL (опционально)
      - status: assigned | unassigned | all (опционально)
      - q: строка поиска по VIN/юниту/комменту (опционально)
      - brand: может быть несколько (brand=gwm&amp;brand=chery), либо одно значение
      - start_date, end_date: YYYY-MM-DD (включительно)
    """
    from django.utils.dateparse import parse_date
    from django.utils import timezone
    from datetime import datetime, timedelta

    ZONE = "Цех сборки"
    # --- входные параметры ---
    grade_filter = (request.GET.get("grade") or "").strip().upper()  # V1, V1+, V2, V3, ALL
    status_filter = (request.GET.get("status") or "").strip().lower()  # assigned | unassigned | all
    if not grade_filter:
        grade_filter = "V1+"
    if not status_filter:
        status_filter = "unassigned"

    query = (request.GET.get("q") or "").strip().lower()

    # Бренды (несколько значений допускается)
    brands_selected = request.GET.getlist("brand") or []
    brands_selected = [b.strip().lower() for b in brands_selected if b and b.strip()]
    # Карта «семейства» брендов в фактические значения из TraceData.brand
    BRAND_MAP = {
        "gwm": ["haval", "tank"],
        "chery": ["chery"],
        "changan": ["changan"],
    }
    mapped_brands = set()
    for b in brands_selected:
        mapped_brands.update(BRAND_MAP.get(b, [b]))

    # Посты (несколько значений допускается)
    posts_selected = request.GET.getlist("post") or []
    posts_selected = [p.strip() for p in posts_selected if p and p.strip()]
    mapped_posts = set(posts_selected)

    # Даты фильтра (включительно)
    start_date = parse_date(request.GET.get("start_date") or "")
    end_date = parse_date(request.GET.get("end_date") or "")
    # если задали только start_date или end_date — используем односторонний коридор

    defects_all = []
    allowed_grades = {"V1+", "V1", "V2", "V3"}

    # --- собираем все дефекты (без фильтра бренда, т.к. нужен TraceData) ---
    for vh in VINHistory.objects.all().iterator():
        vin = vh.vin
        posts = (vh.history or {}).get(ZONE, {})
        if not isinstance(posts, dict):
            continue

        for post_name, entries in posts.items():
            for entry in (entries or []):
                entry_id = entry.get("id")
                controller = entry.get("controller", "") or entry.get("extra_data", {}).get("controller", "")
                raw_date = entry.get("date_added")
                date = parse_datetime(raw_date) if raw_date else None
                date_str_fmt = date.strftime("%d.%m.%Y") if date else ""
                time_str_fmt = localtime(date).strftime("%H:%M") if date else ""
                line = entry.get("line", "")
                duration = entry.get("inspection_duration_seconds", "")

                defs = entry.get("defects", []) or []
                for d in defs:
                    defect_id = d.get("id")
                    grade_raw = d.get("grade", "")
                    grade_norm = (grade_raw or "").strip().upper()
                    if grade_norm not in allowed_grades:
                        continue

                    name = d.get("name") or d.get("defect_description", "Без описания")
                    unit = d.get("unit", "")
                    comment = d.get("comment", "")
                    photos = d.get("photos", []) or []

                    extra = d.get("extra", {}) or {}
                    resp_ids = extra.get("qrr_responsibles_ids") or []
                    resp_names = extra.get("qrr_responsibles") or []
                    if not isinstance(resp_ids, list):
                        resp_ids = [resp_ids] if resp_ids else []
                    if not isinstance(resp_names, list):
                        resp_names = [resp_names] if resp_names else []
                    qrr_set_by = extra.get("qrr_set_by") or ""
                    qrr_set_at = extra.get("qrr_set_at") or ""
                    qrr_responsible_fio = extra.get("qrr_responsible_fio") or ""

                    qrr_set_dt = parse_datetime(qrr_set_at) if qrr_set_at else None
                    qrr_set_date_str = qrr_set_dt.strftime("%d.%m.%Y") if qrr_set_dt else ""
                    qrr_set_time_str = localtime(qrr_set_dt).strftime("%H:%M") if qrr_set_dt else ""

                    has_any_resp = bool(resp_names) or bool(resp_ids)

                    card = {
                        # базовые для таблицы
                        "date": date,
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
                        # доп. для QRR UI
                        "vin": vin,
                        "zone": ZONE,
                        "post": post_name,
                        "entry_id": entry_id,
                        "defect_id": defect_id,
                        "extra": extra,
                        "date_added": raw_date,
                        "controller_raw": controller,
                        "qrr_responsibles_ids": resp_ids,
                        "qrr_responsibles": resp_names,
                        "qrr_set_by": qrr_set_by,
                        "qrr_set_at": qrr_set_at,
                        "qrr_responsible_fio": qrr_responsible_fio,
                        "qrr_set_date_str": qrr_set_date_str,
                        "qrr_set_time_str": qrr_set_time_str,
                        "has_any_resp": has_any_resp,
                    }

                    # Текстовый поиск — сразу отфильтруем
                    if query:
                        hay = f"{vin} {post_name} {name} {unit} {comment} {' '.join(map(str, resp_names))}".lower()
                        if query not in hay:
                            continue

                    defects_all.append(card)

    # --- Подтягиваем brand/model/config_code для всех VIN в выборке ---
    vin_list_all = list({(d.get("vin") or "").upper() for d in defects_all if d.get("vin")})
    vin_trace_map = {}
    if TraceData and vin_list_all:
        for td in TraceData.objects.filter(vin_rk__in=vin_list_all):
            key = (getattr(td, "vin_rk", "") or "").upper()
            vin_trace_map[key] = {
                "brand": (getattr(td, "brand", "") or "").lower(),
                "model": getattr(td, "model", "") or "",
                "config_code": getattr(td, "config_code", "") or "",
                "color_1c": getattr(td, "color_1c", "") or "",
            }
    # обогатим карточки
    for d in defects_all:
        vkey = (d.get("vin") or "").upper()
        info = vin_trace_map.get(vkey)
        if info:
            d["brand"] = info["brand"]
            d["model"] = info["model"]
            d["config_code"] = info["config_code"]
            d["color_1c"] = info.get("color_1c", "")
        else:
            d["brand"] = d.get("brand", "")

    # --- Базовые фильтры: бренд и дата (статус не учитываем для корректных счётчиков грейдов) ---
    def _brand_ok(card):
        if not mapped_brands:
            return True
        b = (card.get("brand") or "").lower()
        return bool(b) and (b in mapped_brands)

    def _date_ok(card):
        if not (start_date or end_date):
            return True
        dt = card.get("date")
        if not dt:
            return False
        d = timezone.localtime(dt).date() if timezone.is_aware(dt) else dt.date()
        if start_date and d < start_date:
            return False
        if end_date and d > end_date:
            return False
        return True

    def _post_ok(card):
        if not mapped_posts:
            return True
        p = card.get("post") or ""
        return p in mapped_posts

    filtered_base = [c for c in defects_all if _brand_ok(c) and _date_ok(c) and _post_ok(c)]

    # --- Счётчики по грейдам (после бренд/дата/поиска, но БЕЗ статуса) ---
    counts_grade_total = {}
    counts_grade_unassigned = {}
    counts_grade_assigned = {}
    for c in filtered_base:
        g = c.get("grade") or ""
        counts_grade_total[g] = counts_grade_total.get(g, 0) + 1
        if c.get("has_any_resp"):
            counts_grade_assigned[g] = counts_grade_assigned.get(g, 0) + 1
        else:
            counts_grade_unassigned[g] = counts_grade_unassigned.get(g, 0) + 1

    # --- Затем применяем фильтр по грейду ---
    def _grade_ok(card):
        if not grade_filter or grade_filter == "ALL":
            return True
        return (card.get("grade") or "").upper() == grade_filter

    filtered_by_grade = [c for c in filtered_base if _grade_ok(c)]

    # --- Счётчики по статусам для текущего грейда ---
    counts_status_unassigned = sum(1 for c in filtered_by_grade if not c.get("has_any_resp"))
    counts_status_assigned = sum(1 for c in filtered_by_grade if c.get("has_any_resp"))
    counts_status_all = len(filtered_by_grade)

    # --- Теперь применяем фильтр статуса к выдаче ---
    status_filter = status_filter or "all"
    if status_filter == "assigned":
        defects = [c for c in filtered_by_grade if c.get("has_any_resp")]
    elif status_filter == "unassigned":
        defects = [c for c in filtered_by_grade if not c.get("has_any_resp")]
    else:
        defects = filtered_by_grade

    # Сортировка по дате убыв.
    def _key_date(d):
        dt = d.get("date")
        if dt is None:
            try:
                return timezone.make_aware(datetime.min, timezone.get_current_timezone())
            except Exception:
                return timezone.now() - timezone.timedelta(days=365 * 100)
        return timezone.localtime(dt) if timezone.is_aware(dt) else timezone.make_aware(dt, timezone.get_current_timezone())

    defects.sort(key=_key_date, reverse=True)

    # --- Pagination (default 50 per page) ---
    try:
        page_size = int(request.GET.get("page_size", 50))
    except Exception:
        page_size = 50
    if page_size < 1:
        page_size = 50
    if page_size > 200:
        page_size = 200

    try:
        page = int(request.GET.get("page", 1))
    except Exception:
        page = 1
    if page < 1:
        page = 1

    total = len(defects)
    total_pages = (total + page_size - 1) // page_size if page_size else 1
    start = (page - 1) * page_size
    end = start + page_size
    defects_page = defects[start:end]

    # Группировка по грейду для вкладок — только текущая страница
    grouped = defaultdict(list)
    for d in defects_page:
        gk = d.get("grade") or "Без грейда"
        grouped[gk].append(d)

    grades_tabs = ["V1+", "V1", "V2", "V3"]
    grades_all = ["V1+", "V1", "V2", "V3"]
    for _g in grades_tabs:
        grouped.setdefault(_g, [])

    # Все доступные ответственные QRR
    qrr_responsibles_all = list(QRRResponsible.objects.all().order_by("name").values("id", "name"))

    # Доступные посты для фильтра (по всей выборке до фильтра постов)
    available_posts = sorted({(c.get("post") or "") for c in defects_all if c.get("post")})

    return render(request, "qrr/defects_board.html", {
        "defects": defects_page,
        "grouped": grouped,
        "grade_filter": grade_filter or "",
        "status_filter": status_filter or "",
        "query": query or "",
        "grades": grades_tabs,
        "grades_all": grades_all,
        "vin_trace_map": vin_trace_map,
        "qrr_responsibles_all": qrr_responsibles_all,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "counts_grade_total": counts_grade_total,
        "counts_grade_assigned": counts_grade_assigned,
        "counts_grade_unassigned": counts_grade_unassigned,
        "counts_total": sum(counts_grade_total.values()) if counts_grade_total else 0,
        # новые параметры для шаблона:
        "brands_selected": brands_selected,
        "start_date": start_date,
        "end_date": end_date,
        "mapped_brands": sorted(mapped_brands),
        "counts_status_all": counts_status_all,
        "counts_status_assigned": counts_status_assigned,
        "counts_status_unassigned": counts_status_unassigned,
        "available_posts": available_posts,
        "posts_selected": posts_selected,
    })


def _vin_from_defect_id(defect_id: str) -> str:
    return defect_id.split("-", 1)[0] if defect_id and "-" in defect_id else ""


@login_required
@require_POST
def api_qrr_set_defect_responsible(request):

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    defect_id = payload.get("defect_id")
    responsibles = payload.get("responsibles")  # required: list of IDs or names
    justification = payload.get("justification")  # опционально: обоснование назначения
    extra_fields = payload.get("extra", {}) or {}

    if not defect_id or not isinstance(responsibles, list) or not responsibles:
        return JsonResponse({"ok": False, "error": "required: defect_id and non-empty responsibles[]"}, status=400)

    vin = _vin_from_defect_id(defect_id)
    if not vin:
        return JsonResponse({"ok": False, "error": "bad_defect_id"}, status=400)

    try:
        vh = VINHistory.objects.get(vin=vin)
    except VINHistory.DoesNotExist:
        return JsonResponse({"ok": False, "error": "vin_not_found"}, status=404)

    # Normalize responsibles into ids and names (resolve IDs to names)
    ids_list, id_candidates, name_candidates = [], [], []

    for r in responsibles:
        if isinstance(r, int):
            id_candidates.append(r)
        elif isinstance(r, str):
            rr = r.strip()
            try:
                id_candidates.append(int(rr))
            except Exception:
                if rr:
                    name_candidates.append(rr)
        else:
            name_candidates.append(str(r))

    names_list = []

    if id_candidates:
        qs = QRRResponsible.objects.filter(id__in=id_candidates)
        ids_list = [obj.id for obj in qs]
        names_list.extend(obj.name for obj in qs)

    if name_candidates:
        qs2 = QRRResponsible.objects.filter(name__in=name_candidates)
        ids_list.extend([obj.id for obj in qs2])
        names_list.extend([obj.name for obj in qs2])
        # На случай, если пришли имена, которых нет в справочнике — можно сохранить их «как есть»
        leftover = set(name_candidates) - set(qs2.values_list("name", flat=True))
        names_list.extend(leftover)

    meta = {
        "qrr_responsibles_ids": ids_list,
        "qrr_responsibles": names_list,
        "qrr_set_by": request.user.get_username(),
        "qrr_set_at": timezone.now().isoformat(),
    }
    if justification:
        meta["qrr_responsible_justification"] = justification
    meta.update(extra_fields)

    ok = vh.update_defect_extra(defect_id, **meta)
    return JsonResponse({"ok": bool(ok)})


# BULK API for setting responsibles
@login_required
@require_POST
def api_qrr_set_defect_responsible_bulk(request):

    """
    Batch-assign responsibles to many defects at once.
    Payload example:
    {
      "items": [
        {"defect_id": "<id>", "responsibles": [1,2,"Иванов"], "justification": "...", "extra": {"note": "..."}},
        {"defect_id": "<id2>", "responsibles": ["Петров"]}
      ]
    }
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    items = payload.get("items")
    if not items or not isinstance(items, list):
        return JsonResponse({"ok": False, "error": "required: items[]"}, status=400)

    results = []
    # group by VIN to reduce queries
    buckets = {}
    for it in items:
        did = (it or {}).get("defect_id")
        if not did:
            results.append({"defect_id": None, "ok": False, "error": "no_defect_id"})
            continue
        vin = _vin_from_defect_id(did)
        if not vin:
            results.append({"defect_id": did, "ok": False, "error": "bad_defect_id"})
            continue
        buckets.setdefault(vin, []).append(it)

    for vin, pack in buckets.items():
        try:
            vh = VINHistory.objects.get(vin=vin)
        except VINHistory.DoesNotExist:
            for it in pack:
                results.append({"defect_id": it.get("defect_id"), "ok": False, "error": "vin_not_found"})
            continue

        for it in pack:
            did = it.get("defect_id")
            responsibles = it.get("responsibles")
            if isinstance(responsibles, str):
                responsibles = [responsibles]
            if not responsibles or not isinstance(responsibles, list):
                results.append({"defect_id": did, "ok": False, "error": "no_responsibles"})
                continue

            justification = it.get("justification")
            extra_fields = (it.get("extra") or {})

            # reuse single-item logic by resolving IDs/names the same way as in api_qrr_set_defect_responsible
            id_candidates, name_candidates = [], []
            for r in responsibles:
                if isinstance(r, int):
                    id_candidates.append(r)
                elif isinstance(r, str):
                    rr = r.strip()
                    try:
                        id_candidates.append(int(rr))
                    except Exception:
                        if rr:
                            name_candidates.append(rr)
                else:
                    name_candidates.append(str(r))

            ids_list, names_list = [], []
            if id_candidates:
                qs = QRRResponsible.objects.filter(id__in=id_candidates)
                ids_list = [obj.id for obj in qs]
                names_list.extend(obj.name for obj in qs)
            if name_candidates:
                qs2 = QRRResponsible.objects.filter(name__in=name_candidates)
                ids_list.extend([obj.id for obj in qs2])
                names_list.extend([obj.name for obj in qs2])
                leftover = set(name_candidates) - set(qs2.values_list("name", flat=True))
                names_list.extend(leftover)

            meta = {
                "qrr_responsibles_ids": ids_list,
                "qrr_responsibles": names_list,
                "qrr_set_by": request.user.get_username(),
                "qrr_set_at": timezone.now().isoformat(),
            }
            if justification:
                meta["qrr_responsible_justification"] = justification
            meta.update(extra_fields)

            ok = vh.update_defect_extra(did, **meta)
            results.append({"defect_id": did, "ok": bool(ok)})

    return JsonResponse({"ok": True, "results": results})


@login_required
@require_POST
def api_qrr_change_defect_grade(request):

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    defect_id = payload.get("defect_id")
    new_grade = payload.get("grade")
    justification = payload.get("justification")

    if not defect_id or not new_grade:
        return JsonResponse({"ok": False, "error": "required: defect_id, grade"}, status=400)
    if not justification:
        return JsonResponse({"ok": False, "error": "required: justification"}, status=400)

    vin = _vin_from_defect_id(defect_id)
    if not vin:
        return JsonResponse({"ok": False, "error": "bad_defect_id"}, status=400)

    try:
        vh = VINHistory.objects.get(vin=vin)
    except VINHistory.DoesNotExist:
        return JsonResponse({"ok": False, "error": "vin_not_found"}, status=404)

    # Перезаписываем основной grade и заносим justification в extra
    ok = vh.set_qrr_for_defect(
        defect_id=defect_id,
        grade=new_grade,
        overwrite_main=True,
        qrr_grade_changed_by=request.user.get_username(),
        qrr_grade_changed_at=timezone.now().isoformat(),
        qrr_grade_justification=justification,
    )
    return JsonResponse({"ok": bool(ok)})
