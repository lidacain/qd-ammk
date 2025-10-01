import qrcode
import os


post_id = 2
post_url = f"MXMDB21B6SK097087"

# Генерация QR-кода
qr = qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_L,
    box_size=10,
    border=4,
)
qr.add_data(post_url)
qr.make(fit=True)

# Создание изображения QR-кода
img = qr.make_image(fill="black", back_color="white")

output_dir = "VIN_QR"
os.makedirs(output_dir, exist_ok=True)

# Путь к файлу
qr_filename = os.path.join(output_dir, f"{post_url}.png")
img.save(qr_filename)

print(f"QR-код сохранен как {qr_filename}")