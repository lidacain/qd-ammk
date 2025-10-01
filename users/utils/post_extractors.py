# users/utils/post_extractors.py
from collections import defaultdict
from django.utils.dateparse import parse_datetime
from vehicle_history.models import AssemblyPassLog, VESPassLog

def _dt(val):
    try:
        dt = parse_datetime(val)
        return dt.replace(second=0, microsecond=0) if dt else None
    except Exception:
        return None

def _iter_defects_with_parent_dt(history_data):
    """Yield (normalized_defect_dict, parent_dt) for ALL posts except UUD itself."""
    for zone_name, zone in (history_data or {}).items():
        for post_name, entries in (zone or {}).items():
            if zone_name == "УУД":
                continue
            for entry in (entries or []):
                pdt = _dt(entry.get("date_added") or entry.get("added_at"))
                if not pdt:
                    continue
                defects, _ = _collect_defects(entry)
                for d in defects:
                    yield d, pdt


def _uud_status_snapshot(defect, cutoff):
    """From defect.extra.UUD.history take the latest decision at or before cutoff.
    Returns dict with keys: status, decided_at, decided_by, fix_at, fix_by, fix_kind, fix_comment, fix_photos.
    """
    snap = {"status": None, "decided_at": None, "decided_by": None,
            "fix_at": None, "fix_by": None, "fix_kind": None, "fix_comment": None, "fix_photos": []}
    extra = (defect.get("extra") or {})
    uud = (extra.get("UUD") or {})
    hist = uud.get("history") or []
    best_t = None
    for h in hist:
        dec = (h or {}).get("decision", {})
        at = _dt(dec.get("at"))
        if cutoff and at and at <= cutoff and (best_t is None or at > best_t):
            best_t = at
            snap["status"] = dec.get("status")
            snap["decided_at"] = at
            snap["decided_by"] = dec.get("by")
            fix = (h or {}).get("fix", {})
            snap["fix_at"] = _dt(fix.get("at"))
            snap["fix_by"] = fix.get("by")
            snap["fix_kind"] = fix.get("kind")
            snap["fix_comment"] = fix.get("comment")
            snap["fix_photos"] = fix.get("photos", [])
    return snap

def _collect_defects(entry):
    """Привести дефекты к единому виду и вычислить флаги."""
    out = []
    has_uud_impossible_here = False
    defects = entry.get("defects", []) or []
    if isinstance(defects, list):
        for d in defects:
            if isinstance(d, dict):
                # --- Normalize defect fields across formats ---
                # New assembly format may use: name/unit/zone/grade/photos
                # Supply (DKD) format uses: defect/detail/defect_photos, custom_* and responsible
                extra = d.get("extra", {}) or {}
                uud  = extra.get("UUD", {}) or {}
                status = (uud.get("status") or "").lower()
                if status == "impossible":
                    has_uud_impossible_here = True

                name = d.get("name") or d.get("defect")
                unit = d.get("unit") or ""
                zone = d.get("zone") or d.get("detail")
                photos = d.get("photos") or d.get("defect_photos") or []

                # enrich extra with DKD-specific meta if present
                if "responsible" in d:
                    extra = dict(extra)  # copy to avoid mutating original
                    extra["responsible"] = d.get("responsible")
                if "custom_defect_explanation" in d:
                    extra = dict(extra)
                    extra["custom_defect_explanation"] = d.get("custom_defect_explanation")
                if "custom_detail_explanation" in d:
                    extra = dict(extra)
                    extra["custom_detail_explanation"] = d.get("custom_detail_explanation")

                out.append({
                    "name": name,
                    "unit": unit,
                    "zone": zone,
                    "grade": d.get("grade"),
                    "quantity": d.get("quantity"),
                    "repair_type": d.get("repair_type"),
                    "comment": d.get("comment"),
                    "photos": photos,
                    "extra": extra,
                })
            else:
                out.append({"name": str(d)})
    return out, has_uud_impossible_here

def _base_normalizer(history_data, post):
    """
    Базовый экстрактор: ищет post во всех зонах и группирует по (controller, minute).
    Возвращает entries в едином формате.
    """
    grouped = defaultdict(lambda: {
        "defects": [],
        "photos": {"body": set(), "component": set(), "defect": []},
        "labels": set(),         # для произвольных меток/бейджей
        "steps": [],             # [{step, status, dt}]
        "flags": {
            "uud_impossible": False,
        },
        "extra": {},            # сюда можно сложить что угодно специфичное
    })

    for zone_name, zone_data in (history_data or {}).items():
        for entry in zone_data.get(post, []) or []:
            controller = entry.get("controller") or entry.get("added_by", "")
            dt = _dt(entry.get("date_added") or entry.get("added_at"))
            if not dt:
                continue
            key = (controller, dt)

            g = grouped[key]
            g["controller"] = controller
            g["date"] = dt
            g["zone"] = zone_name

            # статусы/шаги (если приходят)
            for s in entry.get("steps", []) or []:
                g["steps"].append({
                    "step": s.get("step"),
                    "status": s.get("status"),
                    "dt": _dt(s.get("dt")) or dt,
                })

            # дефекты
            defects, has_impossible = _collect_defects(entry)
            g["defects"].extend(defects)
            if has_impossible:
                g["flags"]["uud_impossible"] = True

            if not g.get("status"):
                if defects:  # были дефекты в этой записи
                    g["status"] = "defect"
                else:  # дефектов нет — значит осмотр пройден без замечаний
                    g["status"] = "ok"


            # collect QRR responsibles from defects' extras (assembly posts)
            for _d in defects:
                ex = _d.get("extra", {}) or {}
                resp = ex.get("qrr_responsibles") or []
                if resp:
                    g.setdefault("extra", {}).setdefault("qrr_responsibles", set()).update(resp)
                resp_ids = ex.get("qrr_responsibles_ids") or []
                if resp_ids:
                    g.setdefault("extra", {}).setdefault("qrr_responsibles_ids", set()).update(resp_ids)

            # фото/поля
            g["photos"]["body"].update(entry.get("body_photos", []) or [])
            g["photos"]["component"].update(entry.get("component_photos", []) or [])
            if entry.get("defect_photos"):
                g["photos"]["defect"].extend(entry.get("defect_photos") or [])
            if entry.get("photos"):
                g["photos"]["defect"].extend(entry.get("photos") or [])

            # специфичные поля, если встретятся
            if entry.get("engine_photo"):  g["extra"]["engine_photo"]  = entry["engine_photo"]
            if entry.get("engine_number"): g["extra"]["engine_number"] = entry["engine_number"]
            if entry.get("status"):        g["status"] = entry.get("status")  # ok/defect/missing и т.п.
            if entry.get("grade"):         g["grade"]  = entry.get("grade")
            if entry.get("comment"):       g["comment"]= entry.get("comment")

            # DKD-specific fields
            if entry.get("container_number"):
                g["extra"]["container_number"] = entry.get("container_number")

            # Assembly/DKD common fields
            if entry.get("line"):
                g["extra"]["line"] = entry.get("line")
            if entry.get("vin_number"):
                g["extra"]["vin_number"] = entry.get("vin_number")
            if entry.get("inspection_duration_seconds") is not None:
                g["extra"]["inspection_duration_seconds"] = entry.get("inspection_duration_seconds")
            # derive status from has_defect if explicit status is absent
            if not g.get("status"):
                hd = (entry.get("has_defect") or "").lower()
                if hd == "yes":
                    g["status"] = "defect"
                elif hd == "no":
                    g["status"] = "ok"

    # преобразовать в список
    entries = []
    for _, g in grouped.items():
        # normalize sets
        extra = g["extra"] or {}
        if isinstance(extra.get("qrr_responsibles"), set):
            extra["qrr_responsibles"] = sorted(extra["qrr_responsibles"])
        if isinstance(extra.get("qrr_responsibles_ids"), set):
            extra["qrr_responsibles_ids"] = sorted(extra["qrr_responsibles_ids"])

        entries.append({
            "controller": g.get("controller"),
            "date": g.get("date"),
            "zone": g.get("zone"),
            "status": g.get("status"),         # может отсутствовать
            "grade": g.get("grade"),
            "comment": g.get("comment"),
            "defects": g["defects"],
            "photos": {
                "body": sorted(g["photos"]["body"]),
                "component": sorted(g["photos"]["component"]),
                "defect": g["photos"]["defect"],
            },
            "steps": sorted(g["steps"], key=lambda x: (x["dt"], x["step"]) if x["dt"] else (0, x["step"] or 0)),
            "flags": g["flags"],
            "extra": extra,
            "labels": sorted(g["labels"]),
        })
    # последний выше
    entries.sort(key=lambda x: x["date"] or _dt("1970-01-01T00:00:00Z"), reverse=True)
    return entries

# --- Специализированные экстракторы (при необходимости) ---

def extractor_trim_in(history_data, post, vin=None):
    """TRIM IN хранится в AssemblyPassLog: для VIN вернуть проходы.
    Вернём список entries совместимого формата: controller=saved_by, date=scanned_at, labels=[LINE].
    """
    items = []
    if not vin:
        return items
    qs = (AssemblyPassLog.objects.filter(vin__iexact=vin)
          .select_related('saved_by')
          .order_by('-scanned_at'))
    for rec in qs:
        items.append({
            "controller": getattr(rec.saved_by, 'username', None) or (str(rec.saved_by) if rec.saved_by else None),
            "date": rec.scanned_at,
            "zone": "TRIM",
            "status": "ok",  # сам факт прохождения
            "grade": None,
            "comment": None,
            "defects": [],
            "photos": {"body": [], "component": [], "defect": []},
            "steps": [],
            "flags": {"uud_impossible": False},
            "extra": {"line": rec.line, "line_display": rec.get_line_display()},
            "labels": [rec.get_line_display()] if rec.line else [],
        })
    return items

def extractor_ves_given(history_data, post, vin=None):
    """VES — Отдан: берём VESPassLog.given_* для VIN"""
    items = []
    if not vin:
        return items
    qs = VESPassLog.objects.filter(vin=vin).order_by('-given_at')
    for rec in qs:
        items.append({
            "controller": getattr(rec.given_by, 'username', None) or (str(rec.given_by) if rec.given_by else None),
            "date": rec.given_at,
            "zone": "VES",
            "status": "ok",
            "grade": None,
            "comment": None,
            "defects": [],
            "photos": {"body": [], "component": [], "defect": []},
            "steps": [],
            "flags": {"uud_impossible": False},
            "extra": {"kind": "given", "is_closed": rec.is_closed, "duration_sec": rec.duration_seconds},
            "labels": ["VES", "Отдан"],
        })
    return items


def extractor_ves_received(history_data, post, vin=None):
    """VES — Принят: берём VESPassLog.received_* для VIN (только закрытые записи)."""
    items = []
    if not vin:
        return items
    qs = VESPassLog.objects.filter(vin=vin, received_at__isnull=False).order_by('-received_at')
    for rec in qs:
        items.append({
            "controller": getattr(rec.received_by, 'username', None) or (str(rec.received_by) if rec.received_by else None),
            "date": rec.received_at,
            "zone": "VES",
            "status": "ok",
            "grade": None,
            "comment": None,
            "defects": [],
            "photos": {"body": [], "component": [], "defect": []},
            "steps": [],
            "flags": {"uud_impossible": False},
            "extra": {"kind": "received", "given_at": rec.given_at, "duration_sec": rec.duration_seconds},
            "labels": ["VES", "Принят"],
        })
    return items

def extractor_uud_step(history_data, post, vin=None, step_index=1):
    """Build entries for UUD steps. For each UUD session take step{n}_at/by as the card
    and attach all defects that existed up to that cutoff. For steps >=3 also attach
    the UUD decision snapshot as of that cutoff to each defect (in d["extra"]["uud_snapshot"]).
    """
    items = []
    # Collect UUD sessions
    sessions = []
    for entry in (history_data.get("УУД", {}) or {}).get("УУД", []) or []:
        ed = entry.get("extra_data", {}) or {}
        at_key = f"step{step_index}_at"
        by_key = f"step{step_index}_by"
        at = _dt(ed.get(at_key))
        if not at:
            continue
        sessions.append({
            "date": at,
            "controller": ed.get(by_key),
        })
    # Sort by date desc (latest first)
    sessions.sort(key=lambda x: x["date"], reverse=True)

    # Pre-collect all defects with their parent timestamps
    all_defects = list(_iter_defects_with_parent_dt(history_data))

    for sess in sessions:
        cutoff = sess["date"]
        defects_for_step = []
        for d, pdt in all_defects:
            if pdt and pdt <= cutoff:
                d2 = dict(d)
                # For steps 3 and 4 include UUD snapshot "as-of" cutoff
                if step_index >= 3:
                    snap = _uud_status_snapshot(d2, cutoff)
                    d2.setdefault("extra", {})["uud_snapshot"] = snap
                defects_for_step.append(d2)
        # derive step status so UI doesn't show MISSING
        step_status = "ok"
        # for any step: if by the cutoff there exists an UUD decision 'impossible' -> dc_repair
        for d in defects_for_step:
            snap = (d.get("extra") or {}).get("uud_snapshot")
            if not snap and step_index >= 3:
                # ensure snapshot is present for steps >=3
                snap = _uud_status_snapshot(d, cutoff)
                d.setdefault("extra", {})["uud_snapshot"] = snap
            if snap and (snap.get("status") or "").lower() == "impossible":
                step_status = "dc_repair"
                break
        items.append({
            "controller": sess.get("controller"),
            "date": cutoff,
            "zone": "УУД",
            "status": step_status,
            "grade": None,
            "comment": None,
            "defects": defects_for_step,
            "photos": {"body": [], "component": [], "defect": []},
            "steps": [],
            "flags": {"uud_impossible": any((d.get("extra", {}).get("UUD", {}) or {}).get("status") == "impossible" for d, _ in all_defects if _ and _ <= cutoff)},
            "extra": {"uud_step": step_index},
            "labels": [f"УУД: Шаг {step_index}"],
        })
    return items

# UUD named extractors (wrappers)

def extractor_uud_step1(history_data, post, vin=None):
    return extractor_uud_step(history_data, post, vin=vin, step_index=1)

def extractor_uud_step2(history_data, post, vin=None):
    return extractor_uud_step(history_data, post, vin=vin, step_index=2)

def extractor_uud_step3(history_data, post, vin=None):
    return extractor_uud_step(history_data, post, vin=vin, step_index=3)

def extractor_uud_step4(history_data, post, vin=None):
    return extractor_uud_step(history_data, post, vin=vin, step_index=4)

def extractor_documentation(history_data, post, vin=None):
    # Build base Documentation entries first (handles added_by/photos/added_at via base normalizer changes)
    items = _base_normalizer(history_data, post)

    # Collect all defects with UUD.status == 'impossible' from entire history
    impossible = []
    for zone_name, zone_data in (history_data or {}).items():
        for post_name, entries in (zone_data or {}).items():
            for entry in (entries or []):
                for d in (entry.get("defects") or []):
                    if not isinstance(d, dict):
                        continue
                    extra = d.get("extra", {}) or {}
                    uud = extra.get("UUD", {}) or {}
                    if (uud.get("status") or "").lower() == "impossible":
                        impossible.append({
                            "post": post_name,
                            "zone": d.get("zone") or d.get("detail"),
                            "name": d.get("name") or d.get("defect"),
                            "unit": d.get("unit") or d.get("detail"),
                            "grade": d.get("grade"),
                            "photos": d.get("photos") or d.get("defect_photos") or [],
                            "comment": d.get("comment"),
                            "detected_at": _dt(entry.get("date_added") or entry.get("added_at")),
                            "detected_by": entry.get("controller") or entry.get("added_by"),
                            "qrr_responsibles": (extra.get("qrr_responsibles") or []),
                            "qrr_responsibles_ids": (extra.get("qrr_responsibles_ids") or []),
                        })

    # Attach the list to every Documentation card; set status to dc_repair if any
    has_impossible = len(impossible) > 0
    for it in items:
        it.setdefault("extra", {})["impossible_defects"] = impossible
        # Also surface them as regular defects so template shows them
        if impossible:
            norm = []
            for d in impossible:
                norm.append({
                    "name": d.get("name"),
                    "unit": d.get("unit") or "",
                    "zone": d.get("zone"),
                    "grade": d.get("grade"),
                    "quantity": None,
                    "repair_type": None,
                    "comment": d.get("comment"),
                    "photos": d.get("photos", []),
                    "extra": {
                        "source_post": d.get("post"),
                        "source_zone": d.get("zone"),
                        "uud_snapshot": {"status": "impossible"},
                        "qrr_responsibles": d.get("qrr_responsibles") or [],
                        "qrr_responsibles_ids": d.get("qrr_responsibles_ids") or [],
                        "detected_at": d.get("detected_at"),
                        "detected_by": d.get("detected_by"),
                    },
                })
            # append to defects list (or create it)
            cur = it.get("defects") or []
            it["defects"] = cur + norm
        if has_impossible:
            it.setdefault("flags", {})["uud_impossible"] = True
            it["status"] = "dc_repair"
    return items

def extractor_assembly_generic(history_data, post, vin=None):
    """Generic extractor for assembly shop posts (same storage as examples).
    Uses base normalizer and keeps enriched fields (line, has_defect→status, qrr responsibles).
    """
    return _base_normalizer(history_data, post)

# Реестр: ключ — имя поста
POST_EXTRACTORS = {
    "TRIM IN": extractor_trim_in,
    "Документация": extractor_documentation,
    "VES — Отдан": extractor_ves_given,
    "VES — Принят": extractor_ves_received,

    "УУД — Шаг 1 (отдана на УУД)": extractor_uud_step1,
    "УУД — Шаг 2 (принята на УУД)": extractor_uud_step2,
    "УУД — Шаг 3 (отдана на линию)": extractor_uud_step3,
    "УУД — Шаг 4 (принята на линию)": extractor_uud_step4,

    # Assembly posts (generic handling)
    "Пост момента затяжек": extractor_assembly_generic,
    "Chassis": extractor_assembly_generic,
    "Финал текущий контроль": extractor_assembly_generic,
    "Зазоры и перепады": extractor_assembly_generic,
    "Экстерьер": extractor_assembly_generic,
    "Интерьер": extractor_assembly_generic,
    "Багажник": extractor_assembly_generic,
    "Мотор": extractor_assembly_generic,
    "Функцонал": extractor_assembly_generic,
    "Геометрия колес": extractor_assembly_generic,
    "Регулировка света фар и калибровка руля": extractor_assembly_generic,
    "Тормозная система": extractor_assembly_generic,
    "Underbody": extractor_assembly_generic,
    "ADAS": extractor_assembly_generic,
    "AVM": extractor_assembly_generic,
    "Герметичность кузова": extractor_assembly_generic,
    "Диагностика": extractor_assembly_generic,
    "Тест трек": extractor_assembly_generic,



}

def extract_entries(history_data, post, vin=None):
    fn = POST_EXTRACTORS.get(post, None)
    if fn is None:
        return _base_normalizer(history_data, post)
    # Экстрактор может зависеть от vin (например, TRIM IN)
    return fn(history_data, post, vin=vin)
