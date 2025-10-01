import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# 🔹 Указываем путь к JSON-файлу (файл уже загружен)
CREDENTIALS_FILE = "daring-hash-403304-f75ea5c718bb.json"  # Имя JSON-файла
SPREADSHEET_ID = "1rp8JT2xaT1At86XRUxM_bu2lgY8iCfcJw-xZokdubeY"  # Твой ID таблицы из ссылки

# 🔹 Настраиваем подключение к Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)

# 🔹 Открываем таблицу
sheet = client.open_by_key(SPREADSHEET_ID).sheet1  # Берем первый лист


def save_defect_to_google_sheets(post, container, pallet, detail, defect, container_img, pallet_img, defect_img):
    """
    Функция для записи данных о дефектах в Google Таблицу.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Формат времени
    row = [timestamp, post, container, pallet, detail, defect, container_img, pallet_img, defect_img]

    sheet.append_row(row)  # Добавляем строку в таблицу
    print("✅ Дефект успешно добавлен в Google Таблицу")