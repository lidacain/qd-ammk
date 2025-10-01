import qrcode
import pandas as pd
import os

# Пути

excel_path = r"O:\Companies\Astana Motors Manufacturing Kazakhstan\270_Контрольные карты\Первые листы\Создание ККИА\CreatingKKIA.xlsm"
output_folder = r"O:\Companies\Astana Motors Manufacturing Kazakhstan\270_Контрольные карты\Первые листы\Шаблоны ККИА\QR"

# excel_path = r"O:\Companies\Astana Motors Manufacturing Kazakhstan\270_Контрольные карты\Создание ККИА\CreatingKKIA.xlsm"
# output_folder = r"O:\Companies\Astana Motors Manufacturing Kazakhstan\270_Контрольные карты\Шаблоны ККИА\QR\Changan"

# excel_path = r"O:\Companies\Astana Motors Manufacturing Kazakhstan\270_Контрольные карты\Создание ККИА\CreatingKKIA.xlsm"
# output_folder = r"O:\Companies\Astana Motors Manufacturing Kazakhstan\270_Контрольные карты\Шаблоны ККИА\QR\Chery"


# excel_path = r"O:\Companies\Astana Motors Manufacturing Kazakhstan\090 Quality Assurance\080_Parts\Контрольная карта\HAVAL\Haval.xlsm"
# output_folder = r"O:\Companies\Astana Motors Manufacturing Kazakhstan\090 Quality Assurance\080_Parts\Контрольная карта\HAVAL\QR"

# Создаем папку, если не существует
os.makedirs(output_folder, exist_ok=True)

# Читаем Excel
df = pd.read_excel(excel_path)

# Столбец с VIN может называться по-разному, но предположим "VIN РК" как в Excel
vin_column = "VIN РК"

# Генерация QR для каждого VIN
for vin in df[vin_column].dropna().unique():
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(vin)
    qr.make(fit=True)
    img = qr.make_image(fill="black", back_color="white")

    qr_path = os.path.join(output_folder, f"{vin}.png")
    img.save(qr_path)
    print(f"✅ QR сохранён: {qr_path}")