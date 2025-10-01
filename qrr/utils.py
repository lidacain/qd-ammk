from datetime import datetime
from django.utils.timezone import localtime
from .models import QRRInvestigation
from vehicle_history.models import VINHistory


def create_qrr_investigation_from_entry(vin: str, station: str, entry: dict, created_by=None) -> QRRInvestigation:
    """
    Создаёт бланк расследования дефектов (БРД) на основе записи из VINHistory.
    :param vin: VIN автомобиля
    :param station: Название станции (пример: "Цех поставки / Зона основной приемки DKD")
    :param entry: Словарь с дефектами (из JSON-поля history)
    :param created_by: Пользователь, создавший БРД
    :return: Объект QRRInvestigation
    """
    defects = entry.get("defects", [])
    if not defects:
        raise ValueError("Нельзя создать БРД без дефектов.")

    defect = defects[0]  # Пока берём только первый дефект

    # Парсим дату
    date_str = entry.get("date_added")
    try:
        form_datetime = datetime.fromisoformat(date_str)
        form_date = form_datetime.date()
        form_time = localtime(form_datetime).time()
    except Exception:
        form_date = None
        form_time = None

    # Генерация номера БРД (в формате YYYY-MM-XXX)
    today_str = form_date.strftime("%Y-%m") if form_date else datetime.today().strftime("%Y-%m")
    last_number = QRRInvestigation.objects.filter(form_number__startswith=today_str).count() + 1
    form_number = f"{today_str}-{str(last_number).zfill(3)}"

    # Создание объекта
    investigation = QRRInvestigation.objects.create(
        vin_history=VINHistory.objects.get(vin=vin),
        created_by=created_by,
        form_number=form_number,
        form_date=form_date,
        form_time=form_time,
        shift="day",  # Можно обновлять на форме
        inspector=entry.get("controller", ""),
        brand="",  # Неизвестно из entry
        model="",  # Неизвестно из entry
        station=station,
        vin=vin,
        grade=defect.get("grade", ""),
        defect_text=defect.get("defect", ""),
        inspection_standard="",
        check_method="",
        value="",
        standard_criteria="",
        qtf_nominal="",
        defect_description=defect.get("custom_defect_explanation", ""),
        defect_photo = defect.get("defect_photos")[0] if defect.get("defect_photos") else None,
        repair_method=defect.get("repair_type", ""),
    )

    return investigation
