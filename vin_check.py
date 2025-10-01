from vehicle_history.models import VINHistory
from django.utils.dateparse import parse_date
from datetime import date

start_date = date(2025, 7, 1)
end_date = date(2025, 8, 2)

vin_without_defects = set()

for h in VINHistory.objects.all():
    entries = h.history.get("Цех сборки", {}).get("Документация", [])
    if not entries:
        continue

    has_entry_in_range = False
    has_defect = False

    for e in entries:
        d = parse_date(e.get("date_added", "")[:10])
        if not d or not (start_date <= d <= end_date):
            continue

        has_entry_in_range = True
        if str(e.get("has_defect", "")).lower() == "yes":
            has_defect = True
            break

    if has_entry_in_range and not has_defect:
        vin_without_defects.add(h.vin)

print("VIN без дефектов:", vin_without_defects)
print("Всего без дефектов:", len(vin_without_defects))