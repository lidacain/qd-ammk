from django.utils.timezone import now
from zoneinfo import ZoneInfo


def now_almaty_iso():
    return now().astimezone(ZoneInfo("Asia/Almaty")).isoformat()
