import qrcode
import os

# Ссылка на конкретный пост
post_id = 'final_current_control_sub_gwm'
post_url = f"/assembly/final_current_control_sub_gwm/?post_id=13"

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

# Путь к папке qr
output_dir = "qr"
os.makedirs(output_dir, exist_ok=True)

# Путь к файлу
qr_filename = os.path.join(output_dir, f"qr_post_{post_id}.png")
img.save(qr_filename)

print(f"QR-код сохранён в {qr_filename}")