from django import template
register = template.Library()
import locale
from django import template
from django.utils.timezone import localtime


@register.filter
def split(value, separator="—"):
    return value.split(separator)


@register.filter
def strip(value):
    return value.strip() if isinstance(value, str) else value


@register.filter
def duration_fmt(seconds):
    try:
        seconds = int(seconds)
        minutes = seconds // 60
        remaining = seconds % 60
        return f"{minutes} мин {remaining} сек" if minutes else f"{remaining} сек"
    except (ValueError, TypeError):
        return "—"


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def defect_name(value):
    """Возвращает часть до скобки"""
    if "(" in value:
        return value.split("(", 1)[0].strip()
    return value


@register.filter
def defect_unit(value):
    """Возвращает часть в скобках"""
    if "(" in value and ")" in value:
        return value.split("(", 1)[1].replace(")", "").strip()
    return "—"


@register.filter
def format_russian_datetime(value):
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')  # Linux/macOS
    except locale.Error:
        try:
            locale.setlocale(locale.LC_TIME, 'Russian_Russia.1251')  # Windows
        except locale.Error:
            pass

    if not value:
        return ''
    dt = localtime(value)  # Переводим в локальное время (Asia/Almaty)
    return dt.strftime('%d %B %Y г. %H:%M')


@register.filter
def dict_get(d, key):
    return d.get(key)