from vehicle_history.models import VINHistory
from django.db import transaction

@transaction.atomic
def replace_chassis_chery():
    updated_count = 0

    for history_obj in VINHistory.objects.all():
        history_data = history_obj.history
        zone = "Цех сборки"

        if zone in history_data and "Chassis Chery" in history_data[zone]:
            print(f"🔄 VIN: {history_obj.vin} — заменяем 'Chassis Chery' на 'Chassis'")

            # Извлекаем старые записи
            chery_entries = history_data[zone].pop("Chassis Chery")

            # Объединяем с "Chassis", если уже есть
            if "Chassis" in history_data[zone]:
                history_data[zone]["Chassis"].extend(chery_entries)
            else:
                history_data[zone]["Chassis"] = chery_entries

            # Сохраняем изменения
            history_obj.history = history_data
            history_obj.save()
            updated_count += 1

    print(f"\n✅ Всего обновлено записей: {updated_count}")