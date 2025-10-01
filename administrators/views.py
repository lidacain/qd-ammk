from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from .models import UserActivityLog
from django.utils import timezone
from datetime import timedelta, datetime, timezone as dt_timezone
from django.template.loader import render_to_string
from django.http import HttpResponse

from django.db.models import Count, Max
from django.db.models.functions import TruncHour, TruncDate
from django.contrib.auth import get_user_model
from urllib.parse import urlparse
from collections import Counter

User = get_user_model()


def superuser_required(view_func):
    return user_passes_test(lambda u: u.is_superuser)(view_func)

@superuser_required
def activity_dashboard(request):
    # Удаление старых логов
    seven_days_ago = timezone.now() - timedelta(days=7)
    UserActivityLog.objects.filter(timestamp__lt=seven_days_ago).delete()

    # Показ логов
    minutes = int(request.GET.get('minutes', 180))
    since = timezone.now() - timedelta(minutes=minutes)
    logs = UserActivityLog.objects.filter(timestamp__gte=since).order_by('-timestamp')

    if request.GET.get("ajax") == "1":
        html = render_to_string('administrators/partials/_log_rows.html', {'logs': logs})
        return HttpResponse(html)

    return render(request, 'administrators/dashboard.html', {
        'logs': logs
    })


# --- Activity Insights View ---
@superuser_required
def activity_insights(request):
    """
    Дэшборд агрегированных метрик активности.
    Параметры:
      - days: период в днях (по умолчанию 7)
      - online: окно "онлайн" в минутах (по умолчанию 10)
    """
    try:
        days = int(request.GET.get("days", 7))
    except (TypeError, ValueError):
        days = 7
    try:
        online_window_min = int(request.GET.get("online", 10))
    except (TypeError, ValueError):
        online_window_min = 10

    now_ts = timezone.now()
    since = now_ts - timedelta(days=days)

    # Срез логов за период
    qs = UserActivityLog.objects.filter(timestamp__gte=since)

    # Общие метрики
    total_hits = qs.count()
    unique_users_count = qs.values("user").distinct().count()
    unique_ips_count = qs.values("ip_address").distinct().count()

    # --- Последний визит по каждому пользователю + онлайн-статус ---
    # Берём последнюю метку времени на пользователя
    last_seen_rows = (
        qs.values("user", "role")
          .annotate(last_seen=Max("timestamp"))
    )

    # Подгружаем объекты пользователей одной пачкой
    user_ids = [row["user"] for row in last_seen_rows if row["user"] is not None]
    users_map = {u.id: u for u in User.objects.filter(id__in=user_ids)}

    # Для домена/последнего URL и IP возьмём последний лог отдельно (кол-во пользователей обычно невелико)
    online_cutoff = now_ts - timedelta(minutes=online_window_min)
    per_user = []
    for row in last_seen_rows:
        uid = row["user"]
        last_seen = row["last_seen"]
        role = row.get("role") or ""
        user_obj = users_map.get(uid)

        # Последняя запись этого пользователя
        last_log = None
        if uid is not None:
            last_log = (
                UserActivityLog.objects
                .filter(user_id=uid)
                .order_by("-timestamp")
                .first()
            )
        else:
            # для анонимов (user=None) берём последнюю запись в целом по анонимам
            last_log = (
                UserActivityLog.objects
                .filter(user__isnull=True)
                .order_by("-timestamp")
                .first()
            )

        last_ip = last_log.ip_address if last_log else ""
        last_url = last_log.url if last_log else ""
        is_online = bool(last_seen and last_seen >= online_cutoff)

        per_user.append({
            "user": user_obj,
            "user_id": uid,
            "display_name": getattr(user_obj, "get_full_name", lambda: "")() or getattr(user_obj, "username", "Аноним"),
            "role": role,
            "last_seen": last_seen,
            "last_ip": last_ip,
            "last_url": last_url,
            "is_online": is_online,
        })

    # === Полный список всех пользователей с их последним визитом (за всё время) ===
    last_seen_all_rows = (
        UserActivityLog.objects
        .values("user")
        .annotate(last_seen=Max("timestamp"))
        .filter(user__isnull=False)
    )
    last_seen_all_map = {row["user"]: row["last_seen"] for row in last_seen_all_rows}

    all_users_info = []
    all_users_qs = User.objects.all().only("id", "username", "first_name", "last_name", "role")

    for u in all_users_qs:
        uid = u.id
        last_seen_any = last_seen_all_map.get(uid)
        last_log_any = None
        if last_seen_any:
            last_log_any = (
                UserActivityLog.objects
                .filter(user_id=uid)
                .order_by("-timestamp")
                .first()
            )
        all_users_info.append({
            "user": u,
            "display_name": getattr(u, "get_full_name_with_patronymic", lambda: None)() or u.get_full_name() or u.username,
            "role": getattr(u, "role", ""),
            "last_seen": last_seen_any,
            "last_ip": last_log_any.ip_address if last_log_any else "",
            "last_url": last_log_any.url if last_log_any else "",
            "is_online": bool(last_seen_any and last_seen_any >= online_cutoff),
        })

    # Отсортируем общий список по последнему визиту (сначала активные)
    all_users_info.sort(key=lambda x: (x["last_seen"] or datetime.min.replace(tzinfo=dt_timezone.utc)), reverse=True)

    # Отсортируем по последней активности
    per_user.sort(key=lambda x: (x["last_seen"] or datetime.min.replace(tzinfo=dt_timezone.utc)), reverse=True)

    # --- Топ популярных страниц (URL) ---
    top_pages = (
        qs.values("url")
          .annotate(hits=Count("id"))
          .order_by("-hits")[:20]
    )

    # --- Популярные домены ---
    domains = []
    for item in top_pages:
        try:
            d = urlparse(item["url"]).netloc
        except Exception:
            d = ""
        if d:
            domains.append((d, item["hits"]))
    # Дополняем домены, если надо, из общего среза
    if not domains:
        for rec in qs.values_list("url", flat=True):
            try:
                d = urlparse(rec).netloc
            except Exception:
                d = ""
            if d:
                domains.append((d, 1))
    domain_counter = Counter()
    for d, h in domains:
        domain_counter[d] += h
    top_domains = sorted(domain_counter.items(), key=lambda kv: kv[1], reverse=True)[:10]

    popular_url = top_pages[0]["url"] if top_pages else ""
    popular_domain = top_domains[0][0] if top_domains else ""

    # --- Хиты по часам и по дням (для графиков) ---
    by_hour = (
        qs.annotate(ts_hour=TruncHour("timestamp"))
          .values("ts_hour")
          .annotate(hits=Count("id"))
          .order_by("ts_hour")
    )
    by_day = (
        qs.annotate(ts_day=TruncDate("timestamp"))
          .values("ts_day")
          .annotate(hits=Count("id"))
          .order_by("ts_day")
    )

    # --- Статистика по ролям ---
    role_rows = (
        qs.values("role")
          .annotate(hits=Count("id"), users=Count("user", distinct=True))
          .order_by("-hits")
    )

    context = {
        "since": since,
        "until": now_ts,
        "days": days,
        "online_window_min": online_window_min,

        "total_hits": total_hits,
        "unique_users_count": unique_users_count,
        "unique_ips_count": unique_ips_count,

        "per_user": per_user,
        "top_pages": list(top_pages),
        "top_domains": top_domains,
        "popular_url": popular_url,
        "popular_domain": popular_domain,

        "by_hour": list(by_hour),
        "by_day": list(by_day),
        "role_rows": list(role_rows),

        "all_users": all_users_info,
    }

    return render(request, "administrators/activity_insights.html", context)


