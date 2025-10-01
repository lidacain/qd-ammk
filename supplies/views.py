import os
import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.conf import settings
from django.contrib.auth.decorators import login_required
from users.decorators import role_required
from .models import Post, TraceData, Defect, Detail, DefectGrade, DefectResponsible, BodyDetail
from .forms import ContainerUnloadingZone2InspectionForm, ContainerUnloadingZoneSBInspectionForm, ComponentUnloadingZoneDKDForm, BodyUnloadingZoneDKDForm, MainUnloadingZoneDKDForm, ContainerInspectionForm
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from users.models import Notification, CustomUser
from django.utils.timezone import now
from vehicle_history.models import VINHistory, ContainerHistory
from django.http import JsonResponse
from django.db.models import Q
from .models import TraceData
import json
from vehicle_history.utils import now_almaty_iso
from PIL import Image, ImageOps
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys
import time
import os
from urllib.parse import unquote
from django.urls import reverse
import uuid

from uuid import uuid4
from pathlib import Path
from PIL import Image, ImageOps


def compress_uploaded_image(uploaded_file, quality=60, max_width=1600):
    """
    Сжимает изображение и возвращает InMemoryUploadedFile с УНИКАЛЬНЫМ именем.
    Совместимо с Pillow 9/10+ и iPhone (правильный поворот по EXIF).
    """
    try:
        # читаем и правим ориентацию (iPhone), приводим к RGB
        img = Image.open(uploaded_file)
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # ресайз с корректным фильтром (Pillow 10+)
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:          # Pillow <10
            resample = Image.LANCZOS

        if img.width > max_width:
            ratio = max_width / float(img.width)
            new_h = int(img.height * ratio)
            img = img.resize((max_width, new_h), resample)

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        buf.seek(0)

        # уникальное имя: <исходное>_<uuid>.jpg
        orig_name = getattr(uploaded_file, "name", "upload.jpg")
        base = Path(orig_name).stem
        new_filename = f"{base}_{uuid4().hex}.jpg"

        return InMemoryUploadedFile(
            file=buf,
            field_name=None,
            name=new_filename,
            content_type="image/jpeg",
            size=buf.getbuffer().nbytes,
            charset=None,
        )
    except Exception as e:
        print("Ошибка при сжатии:", e)
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        return uploaded_file

# 🔹 Настройки Google Sheets
GOOGLE_SHEETS_CREDENTIALS = os.path.join(settings.BASE_DIR, "daring-hash-403304-f75ea5c718bb.json")  # ✅ Проверь путь
SPREADSHEET_ID = "1rp8JT2xaT1At86XRUxM_bu2lgY8iCfcJw-xZokdubeY"
SHEET_NAME = "Лист1"

# 🔹 Базовый URL медиа-файлов
BASE_MEDIA_URL = "http://127.0.0.1:8000/media/"


def append_to_google_sheets(data):
    """Добавление данных в Google Sheets."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS, scope)
        client = gspread.authorize(creds)

        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        sheet.append_row(data)
        print("✅ Данные успешно добавлены")
    except Exception as e:
        print(f"❌ Ошибка при добавлении данных: {e}")



def view_image(request, image_path):
    """
    Отображает изображение дефекта с возможностью пролистывания в рамках одной записи.
    """
    image_path = unquote(image_path)
    image_url = f"{settings.MEDIA_URL}{image_path}"

    # 🔁 Получаем индекс и список изображений
    group_key = request.GET.get("group")
    try:
        index = int(request.GET.get("index", 0))
    except ValueError:
        index = 0

    photos = [image_url]  # fallback

    if request.GET.get("photos"):
        try:
            photos = json.loads(request.GET.get("photos"))
        except json.JSONDecodeError:
            pass

    # ⚠️ Проверка: файл реально существует
    full_path = os.path.join(settings.MEDIA_ROOT, image_path)
    if not os.path.exists(full_path):
        messages.error(request, "Файл не найден.")
        return redirect("assembly_workshop_dashboard")

    return render(request, "supplies/view_image.html", {
        "image_url": image_url,
        "all_photos": json.dumps(photos),  # 📦 для JS
        "current_index": index,
    })


def search_engine_number(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse({"results": []})

    # Проверяем, есть ли такие номера двигателей в базе
    engines = TraceData.objects.filter(engine_number__icontains=query)[:5]

    if not engines.exists():
        return JsonResponse({"results": [], "error": "Нет данных по этому запросу"})

    results = [
        {
            "engine_number": engine.engine_number,
            "vin": engine.vin_rk,
            "model": engine.model,
            "body_color": engine.body_color
        }
        for engine in engines
    ]

    return JsonResponse({"results": results})


def search_vin(request):
    """
    Поиск информации о кузове по VIN.
    """
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse({"results": []})

    # Поиск по VIN в TraceData (ограничиваем 5 результатами)
    vins = TraceData.objects.filter(vin_rk__icontains=query)[:5]

    if not vins.exists():
        return JsonResponse({"results": [], "error": "Нет данных по этому VIN"})

    results = [
        {
            "vin": vin.vin_rk,
            "engine_number": vin.engine_number,
            "config_code": vin.config_code,
            "model": vin.model,
            "body_color": vin.body_color,
            "drive_type": vin.modification,  # если ты именно это отображаешь как "тип привода"
        }
        for vin in vins
    ]

    return JsonResponse({"results": results})


def vin_defects_api(request):
    vin = request.GET.get("vin")
    if not vin:
        return JsonResponse({"error": "VIN не указан"}, status=400)

    try:
        history_entry = VINHistory.objects.get(vin=vin)
    except VINHistory.DoesNotExist:
        return JsonResponse({"defects": []})  # Если VIN не найден, возвращаем пустой список

    defects_list = []

    # ✅ Перебираем историю и собираем данные по дефектам
    for zone, zone_data in history_entry.history.items():
        for post_name, inspections in zone_data.items():
            for inspection in inspections:
                # ✅ Извлекаем repair_type и repair_type_description на уровне инспекции (если есть)
                inspection_repair_type = inspection.get("repair_type", "Не указано")
                inspection_repair_type_description = inspection.get("repair_type_description", "-")

                for defect in inspection.get("defects", []):
                    # ✅ Проверяем, есть ли repair_type на уровне дефекта (для комплектующих)
                    defect_repair_type = defect.get("repair_type", inspection_repair_type)
                    defect_repair_type_description = defect.get("repair_type_description", inspection_repair_type_description)

                    # ✅ Если repair_type является массивом, соединяем элементы через ", "
                    if isinstance(defect_repair_type, list):
                        defect_repair_type = ", ".join(defect_repair_type)
                    elif not defect_repair_type:
                        defect_repair_type = "Не указано"

                    defects_list.append({
                        "zone": zone,  # ✅ Добавляем зону для понимания
                        "post": post_name,
                        "repair_type": defect_repair_type,
                        "repair_type_description": defect_repair_type_description,  # ✅ Добавляем описание ремонта
                        "grade": defect.get("grade", ""),
                        "detail": defect.get("detail", ""),
                        "custom_detail_explanation": defect.get("custom_detail_explanation", "-"),
                        "defect": defect.get("defect", ""),
                        "custom_defect_explanation": defect.get("custom_defect_explanation", "-"),
                        "quantity": defect.get("quantity", ""),
                        "responsible": defect.get("responsible", ""),
                        "defect_photos": defect.get("defect_photos", []),
                    })

    return JsonResponse({"defects": defects_list})


@login_required
@role_required(["controller", 'master'])
def container_unloading_zone_2(request):
    """
    Представление для инспекции в зоне выгрузки контейнеров (Этаж 2).
    """
    post_id = request.GET.get("post_id")
    post = get_object_or_404(Post, id=post_id)

    if not request.user.is_authenticated:
        messages.error(request, "Ошибка: Вы должны быть авторизованы для фиксации дефекта.")
        return redirect("/login/")

    details = Detail.objects.filter(posts=post)
    defects = Defect.objects.filter(posts=post)

    if request.method == "POST":
        form = ContainerUnloadingZone2InspectionForm(request.POST, request.FILES, post=post)
        if form.is_valid():
            inspection = form.save(commit=False)
            inspection.post = post
            inspection.controller = request.user

            os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/containers"), exist_ok=True)
            os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/pallets"), exist_ok=True)
            os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/defects"), exist_ok=True)

            # ✅ Сохранение фото контейнера
            if "container_image" in request.FILES:
                file = request.FILES["container_image"]
                file_path = f"images/containers/{file.name}"
                with open(os.path.join(settings.MEDIA_ROOT, file_path), "wb+") as destination:
                    for chunk in file.chunks():
                        destination.write(chunk)
                inspection.container_image = file_path

            # ✅ Сохранение фото палеты
            if "pallet_image" in request.FILES:
                file = request.FILES["pallet_image"]
                file_path = f"images/pallets/{file.name}"
                with open(os.path.join(settings.MEDIA_ROOT, file_path), "wb+") as destination:
                    for chunk in file.chunks():
                        destination.write(chunk)
                inspection.pallet_image = file_path

            # ✅ Сохранение дефектных изображений
            defect_image_urls = []
            defect_images = form.cleaned_data["defect_images"]  # ✅ Получаем список файлов

            for file in defect_images:
                file_path = f"images/defects/{file.name}"
                with open(os.path.join(settings.MEDIA_ROOT, file_path), "wb+") as destination:
                    for chunk in file.chunks():
                        destination.write(chunk)
                defect_image_urls.append(f"{BASE_MEDIA_URL}{file_path}")

            inspection.defect_images = ", ".join(defect_image_urls) if defect_image_urls else "-"

            inspection.save()

            # ✅ Отправка данных в Google Sheets
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            container_image_url = f"{BASE_MEDIA_URL}{inspection.container_image}" if inspection.container_image else "-"
            pallet_image_url = f"{BASE_MEDIA_URL}{inspection.pallet_image}" if inspection.pallet_image else "-"

            data = [
                now, post.name, inspection.container_number, inspection.pallet_number,
                inspection.detail.name if inspection.detail else "-",
                inspection.defect.name if inspection.defect else "-",
                container_image_url, pallet_image_url, inspection.defect_images
            ]

            append_to_google_sheets(data)

            messages.success(request, "✅ Дефект успешно сохранен")
            return redirect(f"/supplies/container_unloading_zone_2/?post_id={post.id}")

    else:
        form = ContainerUnloadingZone2InspectionForm(post=post)

    return render(request, "supplies/container_unloading_zone_2.html", {
        "form": form,
        "post": post,
        "details": details,
        "defects": defects,
    })


@login_required
@role_required(["controller", 'master'])
def container_unloading_zone_sb(request):
    """
    Представление для инспекции в зоне выгрузки контейнеров SB.
    """
    if request.method == "POST":
        form = ContainerUnloadingZoneSBInspectionForm(request.POST, request.FILES)
        if form.is_valid():
            inspection = form.save(commit=False)

            # ✅ Назначаем контроллера (пользователя, который вносит дефект)
            inspection.controller = request.user

            # ✅ Получаем пост из параметра запроса и назначаем его объекту
            post_id = request.GET.get("post_id")
            inspection.post = get_object_or_404(Post, id=post_id)

            os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/containers"), exist_ok=True)
            os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/container_numbers"), exist_ok=True)
            os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/container_seals"), exist_ok=True)

            container_image_urls = []
            container_images = form.cleaned_data["container_images"]

            for file in container_images:
                file_path = f"images/containers/{file.name}"
                with open(os.path.join(settings.MEDIA_ROOT, file_path), "wb+") as destination:
                    for chunk in file.chunks():
                        destination.write(chunk)
                container_image_urls.append(f"{settings.MEDIA_URL}{file_path}")

            inspection.container_images = ", ".join(container_image_urls) if container_image_urls else "-"

            if "container_number_image" in request.FILES:
                file = request.FILES["container_number_image"]
                file_path = f"images/container_numbers/{file.name}"
                with open(os.path.join(settings.MEDIA_ROOT, file_path), "wb+") as destination:
                    for chunk in file.chunks():
                        destination.write(chunk)
                inspection.container_number_image = file_path

            if "seal_image" in request.FILES:
                file = request.FILES["seal_image"]
                file_path = f"images/container_seals/{file.name}"
                with open(os.path.join(settings.MEDIA_ROOT, file_path), "wb+") as destination:
                    for chunk in file.chunks():
                        destination.write(chunk)
                inspection.seal_image = file_path

            inspection.save()

            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            container_image_urls = inspection.container_images if inspection.container_images else "-"
            container_number_image_url = f"{settings.MEDIA_URL}{inspection.container_number_image}" if inspection.container_number_image else "-"
            seal_image_url = f"{settings.MEDIA_URL}{inspection.seal_image}" if inspection.seal_image else "-"

            data = [
                now, inspection.container_number, container_image_urls,
                container_number_image_url, inspection.container_description,
                seal_image_url, inspection.seal_description, inspection.container_status
            ]

            append_to_google_sheets(data)

            messages.success(request, "✅ Дефект успешно сохранен")

            if inspection.container_status == "damaged":
                admins_and_masters = CustomUser.objects.filter(role__in=["admin", "master"])
                message = f"Контейнер {inspection.container_number} зафиксирован как поврежденный. Требуется проверка."
                for user in admins_and_masters:
                    Notification.objects.create(recipient=user, message=message, defect=inspection)

            return redirect("/supplies/container_unloading_zone_sb/")

    else:
        form = ContainerUnloadingZoneSBInspectionForm()

    return render(request, "supplies/container_unloading_zone_sb.html", {
        "form": form,
    })


@login_required
@role_required(["controller", 'master'])
def component_unloading_zone_dkd(request):
    post_id = request.GET.get("post_id")
    post = get_object_or_404(Post, id=post_id)

    details = Detail.objects.filter(posts=post)
    defects = Defect.objects.filter(posts=post)
    defect_grades = DefectGrade.objects.all()
    defect_responsibles = DefectResponsible.objects.filter(posts=post)

    if request.method == "POST":
        print("DEBUG: request.POST =", request.POST)
        print("DEBUG: request.FILES =", request.FILES)

        form = ComponentUnloadingZoneDKDForm(request.POST, request.FILES, post_id=post_id)

        if form.is_valid():
            engine_number = form.cleaned_data.get("engine_number")
            if not engine_number:
                messages.error(request, "❌ Ошибка: Номер ДВС обязателен.")
                return redirect(f"/supplies/dvs_unloading_zone_dkd/?post_id={post_id}")

            trace_data = TraceData.objects.filter(engine_number=engine_number).first()
            vin = trace_data.vin_rk if trace_data else None

            if not vin:
                messages.error(request, "❌ Ошибка: VIN RK не найден для указанного ДВС.")
                return redirect(f"/supplies/dvs_unloading_zone_dkd/?post_id={post_id}")

            history_entry, _ = VINHistory.objects.get_or_create(vin=vin)

            # ✅ Получаем название цеха и поста
            zone = post.location
            post_name = post.name

            # ✅ Сохранение фото номера ДВС
            engine_photo_url = None
            if "engine_photo" in request.FILES:
                engine_file = request.FILES["engine_photo"]
                engine_file_path = f"images/engine_numbers/{engine_file.name}"
                os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/engine_numbers"), exist_ok=True)
                with open(os.path.join(settings.MEDIA_ROOT, engine_file_path), "wb+") as destination:
                    for chunk in engine_file.chunks():
                        destination.write(chunk)
                engine_photo_url = f"{settings.MEDIA_URL}{engine_file_path}"

            # ✅ Сохранение фото комплектующих (множественный выбор)
            component_photo_urls = []
            component_photos = request.FILES.getlist("component_photos")

            if component_photos:
                for file in component_photos:
                    file_path = f"images/components/{file.name}"
                    os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/components"), exist_ok=True)
                    with open(os.path.join(settings.MEDIA_ROOT, file_path), "wb+") as destination:
                        for chunk in file.chunks():
                            destination.write(chunk)
                    component_photo_urls.append(f"{settings.MEDIA_URL}{file_path}")

            # ✅ Если дефектов нет, фиксируем только фото и осмотр
            has_defect = request.POST.get("has_defect", "")

            if has_defect == "no":
                inspection_data = {
                    "engine_number": engine_number,
                    "controller": request.user.username,
                    "defects": [],  # без дефектов
                    "engine_photo": engine_photo_url,
                    "component_photos": component_photo_urls,
                    "date_added": now_almaty_iso(),
                }

                if zone not in history_entry.history:
                    history_entry.history[zone] = {}

                if post_name not in history_entry.history[zone]:
                    history_entry.history[zone][post_name] = []

                history_entry.history[zone][post_name].append(inspection_data)
                history_entry.save()

                messages.success(request, "✅ Инспекция без дефектов успешно сохранена!")
                return redirect(f"/supplies/dvs_unloading_zone_dkd/?post_id={post_id}")

            # ✅ Обработка всех дефектов
            defect_index = 1
            while f"responsible_{defect_index}" in request.POST:
                responsible_obj = DefectResponsible.objects.filter(id=request.POST.get(f"responsible_{defect_index}")).first()
                detail_obj = Detail.objects.filter(id=request.POST.get(f"detail_{defect_index}")).first()
                defect_obj = Defect.objects.filter(id=request.POST.get(f"defect_{defect_index}")).first()
                grade_obj = DefectGrade.objects.filter(id=request.POST.get(f"grade_{defect_index}")).first()

                repair_type_value = request.POST.get(f"repair_type_{defect_index}")

                defect_data = {
                    "responsible": responsible_obj.name if responsible_obj else None,
                    "detail": detail_obj.name if detail_obj else None,
                    "defect": defect_obj.name if defect_obj else None,
                    "custom_defect_explanation": request.POST.get(f"custom_defect_explanation_{defect_index}"),
                    "quantity": request.POST.get(f"quantity_{defect_index}", 1),
                    "grade": grade_obj.name if grade_obj else None,
                    "repair_type": repair_type_value,  # ✅ Теперь здесь только один выбор
                    "defect_photos": [],
                }

                # ✅ Сохранение фото дефектов
                defect_photo_urls = []
                defect_images = request.FILES.getlist(f"defect_photos_{defect_index}")
                if defect_images:
                    for file in defect_images:
                        file_path = f"images/defects/{file.name}"
                        os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/defects"), exist_ok=True)
                        with open(os.path.join(settings.MEDIA_ROOT, file_path), "wb+") as destination:
                            for chunk in file.chunks():
                                destination.write(chunk)
                        defect_photo_urls.append(f"{settings.MEDIA_URL}{file_path}")

                defect_data["defect_photos"] = defect_photo_urls

                # ✅ Создаем отдельный inspection_data для каждого дефекта
                inspection_data = {
                    "engine_number": engine_number,
                    "controller": request.user.username,
                    "defects": [defect_data],
                    "engine_photo": engine_photo_url,
                    "component_photos": component_photo_urls,
                    "date_added": now_almaty_iso(),
                }

                # ✅ Добавляем данные в JSON-историю
                if zone not in history_entry.history:
                    history_entry.history[zone] = {}

                if post_name not in history_entry.history[zone]:
                    history_entry.history[zone][post_name] = []

                history_entry.history[zone][post_name].append(inspection_data)
                defect_index += 1

            history_entry.save()

            messages.success(request, "✅ Инспекция успешно сохранена!")
            return redirect(f"/supplies/dvs_unloading_zone_dkd/?post_id={post_id}")

        else:
            messages.error(request, "❌ Ошибка: Проверьте заполненные данные!")
            print("Форма не прошла валидацию:", form.errors)

    else:
        form = ComponentUnloadingZoneDKDForm(post_id=post_id)

    return render(request, "supplies/component_unloading_zone_dkd.html", {
        "form": form,
        "details": details,
        "defects": defects,
        "defect_grades": defect_grades,
        "defect_responsibles": defect_responsibles,
        "post_id": post_id,
        "post": post,
    })


@login_required
@role_required(["controller", 'master'])
def body_unloading_zone_dkd(request):
    post_id = request.GET.get("post_id")
    post = get_object_or_404(Post, id=post_id)

    details = BodyDetail.objects.filter(posts=post)
    defects = Defect.objects.filter(posts=post)
    defect_grades = DefectGrade.objects.all()
    defect_responsibles = DefectResponsible.objects.filter(posts=post)

    if request.method == "POST":
        print("DEBUG: request.POST =", request.POST)
        print("DEBUG: request.FILES =", request.FILES)

        form = BodyUnloadingZoneDKDForm(request.POST, request.FILES, post_id=post_id)

        if form.is_valid():
            vin_number = form.cleaned_data.get("vin_number")
            container_number = form.cleaned_data.get("container_number", "").strip()
            if not vin_number:
                messages.error(request, "❌ Ошибка: VIN номер обязателен.")
                return redirect(f"/supplies/body_unloading_zone_dkd/?post_id={post_id}")

            history_entry, _ = VINHistory.objects.get_or_create(vin=vin_number)

            # ✅ Получаем название цеха и поста
            zone = post.location
            post_name = post.name

            # ✅ Сохранение фото кузова (множество файлов)
            body_photo_urls = []
            body_photos = form.cleaned_data["body_photos"]
            if body_photos:
                for file in body_photos:
                    compressed_file = compress_uploaded_image(file)  # 🔹 Сжатие
                    file_path = f"images/body_photos/{compressed_file.name}"
                    os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/body_photos"), exist_ok=True)
                    with open(os.path.join(settings.MEDIA_ROOT, file_path), "wb+") as destination:
                        for chunk in compressed_file.chunks():
                            destination.write(chunk)
                    body_photo_urls.append(f"{settings.MEDIA_URL}{file_path}")

            has_defect = request.POST.get("has_defect", "")

            if has_defect == "no":
                inspection_data = {
                    "vin_number": vin_number,
                    "controller": request.user.username,
                    "defects": [],  # 🔹 Сюда попадут дефекты, если есть
                    "body_photos": body_photo_urls,
                    "date_added": now_almaty_iso(),
                }

                if container_number:
                    inspection_data["container_number"] = container_number

                # ⏱️ Добавляем длительность осмотра, если она есть
                duration_seconds = request.POST.get("inspection_duration_seconds")
                try:
                    inspection_data["inspection_duration_seconds"] = int(duration_seconds)
                except (ValueError, TypeError):
                    inspection_data["inspection_duration_seconds"] = None

                # ✅ Добавляем данные в JSON-историю
                if zone not in history_entry.history:
                    history_entry.history[zone] = {}

                if post_name not in history_entry.history[zone]:
                    history_entry.history[zone][post_name] = []

                history_entry.history[zone][post_name].append(inspection_data)

                # ✅ Сохраняем историю VIN
                history_entry.save()

                messages.success(request, "✅ Осмотр без дефектов успешно сохранен!")
                return redirect(f"/supplies/body_unloading_zone_dkd/?post_id={post_id}")

            # ✅ Обработка всех дефектов
            defect_index = 1
            while f"responsible_{defect_index}" in request.POST:
                responsible_obj = DefectResponsible.objects.filter(id=request.POST.get(f"responsible_{defect_index}")).first()
                detail_obj = BodyDetail.objects.filter(id=request.POST.get(f"detail_{defect_index}")).first()
                defect_obj = Defect.objects.filter(id=request.POST.get(f"defect_{defect_index}")).first()
                grade_obj = DefectGrade.objects.filter(id=request.POST.get(f"grade_{defect_index}")).first()
                detail_explanation = request.POST.get(f"custom_detail_explanation_{defect_index}", "")  # ✅ Добавили
                defect_explanation = request.POST.get(f"custom_defect_explanation_{defect_index}")  # 🆕 берём пояснение дефекта

                defect_data = {
                    "responsible": responsible_obj.name if responsible_obj else None,
                    "detail": detail_obj.name if detail_obj else None,
                    "custom_detail_explanation": detail_explanation,  # ✅ Добавили
                    "defect": defect_obj.name if defect_obj else None,
                    "custom_defect_explanation": defect_explanation,  # ✅ Пояснение дефекта
                    "quantity": request.POST.get(f"quantity_{defect_index}", 1),
                    "grade": grade_obj.name if grade_obj else None,
                    "repair_type": request.POST.get(f"repair_type_{defect_index}"),  # ← добавили!
                    "defect_photos": [],
                }

                # ✅ Сохранение фото дефектов
                defect_photo_urls = []
                defect_images = request.FILES.getlist(f"defect_photos_{defect_index}")  # 🛠 Исправлено!
                if defect_images:
                    for file in defect_images:
                        compressed_file = compress_uploaded_image(file)  # 🔹 Сжатие
                        file_path = f"images/defects/{compressed_file.name}"
                        os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/defects"), exist_ok=True)
                        with open(os.path.join(settings.MEDIA_ROOT, file_path), "wb+") as destination:
                            for chunk in compressed_file.chunks():
                                destination.write(chunk)
                        defect_photo_urls.append(f"{settings.MEDIA_URL}{file_path}")

                defect_data["defect_photos"] = defect_photo_urls

                # ✅ Создаем отдельный inspection_data для каждого дефекта
                inspection_data = {
                    "vin_number": vin_number,
                    "controller": request.user.username,
                    "defects": [defect_data],
                    "body_photos": body_photo_urls,
                    "date_added": now_almaty_iso(),
                }
                # 🔹 Добавляем номер контейнера, если указан
                if container_number:
                    inspection_data["container_number"] = container_number

                # ⏱️ Добавляем длительность осмотра
                duration_seconds = request.POST.get("inspection_duration_seconds")
                try:
                    inspection_data["inspection_duration_seconds"] = int(duration_seconds)
                except (ValueError, TypeError):
                    inspection_data["inspection_duration_seconds"] = None

                # ✅ Добавляем данные в JSON-историю
                if zone not in history_entry.history:
                    history_entry.history[zone] = {}

                if post_name not in history_entry.history[zone]:
                    history_entry.history[zone][post_name] = []

                history_entry.history[zone][post_name].append(inspection_data)
                defect_index += 1  # Переход к следующему дефекту

            history_entry.save()

            messages.success(request, "✅ Инспекция успешно сохранена!")
            return redirect(f"/supplies/body_unloading_zone_dkd/?post_id={post_id}")

        else:
            messages.error(request, "❌ Ошибка: Проверьте заполненные данные!")
            print("Форма не прошла валидацию:", form.errors)

    else:
        form = BodyUnloadingZoneDKDForm(post_id=post_id)

    return render(request, "supplies/body_unloading_zone_dkd.html", {
        "form": form,
        "details": details,
        "defects": defects,
        "defect_grades": defect_grades,
        "defect_responsibles": defect_responsibles,
        "post_id": post_id,
        "post": post,
    })


@login_required
@role_required(["controller", 'master'])
def main_unloading_zone_dkd(request):
    """Представление для зоны основной приемки DKD (без VIN-фото, но с историей дефектов по VIN)"""

    post_id = request.GET.get("post_id")
    post = get_object_or_404(Post, id=post_id)

    details = BodyDetail.objects.all()
    defects = Defect.objects.filter(posts=post)
    defect_grades = DefectGrade.objects.all()
    defect_responsibles = DefectResponsible.objects.filter(posts=post)

    vin_history = None  # История VIN (если уже есть)

    if request.method == "POST":
        print("DEBUG: request.POST =", request.POST)
        print("DEBUG: request.FILES =", request.FILES)

        form = MainUnloadingZoneDKDForm(request.POST, request.FILES, post_id=post_id)

        if form.is_valid():
            vin_number = form.cleaned_data.get("vin_number")
            if not vin_number:
                messages.error(request, "❌ Ошибка: VIN номер обязателен.")
                return redirect(f"/supplies/main_unloading_zone_dkd/?post_id={post_id}")

            history_entry, _ = VINHistory.objects.get_or_create(vin=vin_number)

            zone = post.location
            post_name = post.name

            # ✅ Сохраняем фото кузова
            body_photo_urls = []
            body_photos = form.cleaned_data["body_photos"]
            if body_photos:
                for file in body_photos:
                    compressed_file = compress_uploaded_image(file)  # 🔹 Сжатие
                    file_path = f"images/body_photos/{compressed_file.name}"
                    os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/body_photos"), exist_ok=True)
                    with open(os.path.join(settings.MEDIA_ROOT, file_path), "wb+") as destination:
                        for chunk in compressed_file.chunks():
                            destination.write(chunk)
                    body_photo_urls.append(f"{settings.MEDIA_URL}{file_path}")

            # ✅ Создаём inspection_data сразу
            inspection_data = {
                "vin_number": vin_number,
                "controller": request.user.username,
                "defects": [],  # 🔹 Сюда попадут дефекты, если есть
                "body_photos": body_photo_urls,
                "date_added": now_almaty_iso(),
            }

            # ⏱️ Добавляем длительность осмотра, если она есть
            duration_seconds = request.POST.get("inspection_duration_seconds")
            try:
                inspection_data["inspection_duration_seconds"] = int(duration_seconds)
            except (ValueError, TypeError):
                inspection_data["inspection_duration_seconds"] = None

            # ✅ Добавляем дефекты, если они есть
            defect_index = 1
            while f"responsible_{defect_index}" in request.POST:
                responsible_obj = DefectResponsible.objects.filter(id=request.POST.get(f"responsible_{defect_index}")).first()
                detail_obj = BodyDetail.objects.filter(id=request.POST.get(f"detail_{defect_index}")).first()
                defect_obj = Defect.objects.filter(id=request.POST.get(f"defect_{defect_index}")).first()
                grade_obj = DefectGrade.objects.filter(id=request.POST.get(f"grade_{defect_index}")).first()

                defect_data = {
                    "responsible": responsible_obj.name if responsible_obj else None,
                    "detail": detail_obj.name if detail_obj else None,
                    "custom_detail_explanation": request.POST.get(f"custom_detail_explanation_{defect_index}"),
                    "defect": defect_obj.name if defect_obj else None,
                    "custom_defect_explanation": request.POST.get(f"custom_defect_explanation_{defect_index}"),
                    "quantity": request.POST.get(f"quantity_{defect_index}", 1),
                    "grade": grade_obj.name if grade_obj else None,
                    "repair_type": request.POST.get(f"repair_type_{defect_index}"),
                    "defect_photos": [],
                }

                # Фото дефектов
                defect_photo_urls = []
                defect_images = request.FILES.getlist(f"defect_photos_{defect_index}")
                if defect_images:
                    for file in defect_images:
                        compressed_file = compress_uploaded_image(file)  # 🔹 Сжатие
                        file_path = f"images/defects/{compressed_file.name}"
                        os.makedirs(os.path.join(settings.MEDIA_ROOT, "images/defects"), exist_ok=True)
                        with open(os.path.join(settings.MEDIA_ROOT, file_path), "wb+") as destination:
                            for chunk in compressed_file.chunks():
                                destination.write(chunk)
                        defect_photo_urls.append(f"{settings.MEDIA_URL}{file_path}")

                defect_data["defect_photos"] = defect_photo_urls

                # Добавляем дефект в inspection_data
                inspection_data["defects"].append(defect_data)
                defect_index += 1

            # ✅ Добавляем inspection_data в историю
            if zone not in history_entry.history:
                history_entry.history[zone] = {}

            if post_name not in history_entry.history[zone]:
                history_entry.history[zone][post_name] = []

            history_entry.history[zone][post_name].append(inspection_data)
            history_entry.save()

            messages.success(request, "✅ Инспекция успешно сохранена!")
            return redirect(f"/supplies/main_unloading_zone_dkd/?post_id={post_id}")

        else:
            messages.error(request, "❌ Ошибка: Проверьте заполненные данные!")
            print("Форма не прошла валидацию:", form.errors)

    else:
        form = MainUnloadingZoneDKDForm(post_id=post_id)

    return render(request, "supplies/main_unloading_zone_dkd.html", {
        "form": form,
        "details": details,
        "defects": defects,
        "defect_grades": defect_grades,
        "defect_responsibles": defect_responsibles,
        "post_id": post_id,
        "post": post,
        "vin_history": vin_history,
    })


def get_body_details_by_zone(request):
    """
    API: Возвращает детали кузова по выбранной зоне.
    Пример запроса: /assembly/api/body-details/?zone=left
    """
    zone = request.GET.get("zone")

    if not zone:
        return JsonResponse({"error": "Параметр 'zone' обязателен."}, status=400)

    # Выбираем детали текущей зоны + "универсальные" детали (например, Прочее)
    details = BodyDetail.objects.filter(Q(zone=zone) | Q(zone="all"))

    results = [{"id": detail.id, "name": detail.name} for detail in details]
    return JsonResponse({"details": results})

@login_required
@role_required(["controller", 'master'])
def container_inspection_dkd(request):
    post_id = request.GET.get("post_id")
    post = get_object_or_404(Post, id=post_id)

    if request.method == "POST":
        form = ContainerInspectionForm(request.POST, request.FILES)

        if form.is_valid():
            container_number = form.cleaned_data["container_number"]
            description = form.cleaned_data["description"]
            has_defect = form.cleaned_data["has_defect"]

            # Сохраняем фото контейнера
            photo_urls = []
            photos = request.FILES.getlist("container_photos")
            if photos:
                for file in photos:
                    folder_path = os.path.join(settings.MEDIA_ROOT, "images/containers")
                    os.makedirs(folder_path, exist_ok=True)

                    file_path = f"images/containers/{file.name}"
                    full_path = os.path.join(settings.MEDIA_ROOT, file_path)
                    with open(full_path, "wb+") as destination:
                        for chunk in file.chunks():
                            destination.write(chunk)

                    photo_urls.append(f"{settings.MEDIA_URL}{file_path}")

            # Получаем или создаем запись по контейнеру
            container_obj, _ = ContainerHistory.objects.get_or_create(container_number=container_number)

            # Добавляем запись в историю
            container_obj.add_entry(
                post=post,
                controller_username=request.user.username,
                has_defect=has_defect,
                description=description,
                photos=photo_urls,
                date_added=now_almaty_iso(),  # ⏱️ Берем время из utils
            )

            messages.success(request, "✅ Данные успешно сохранены!")
            return redirect(f"/supplies/container_inspection_dkd/?post_id={post_id}")

        else:
            messages.error(request, "❌ Ошибка: Проверьте заполненные поля!")
    else:
        form = ContainerInspectionForm()

    return render(request, "supplies/container_inspection_dkd.html", {
        "form": form,
        "post_id": post_id,
        "post": post,
    })


def search_container(request):
    query = request.GET.get("q", "").strip()

    if not query:
        return JsonResponse({"results": []})

    containers = (
        ContainerHistory.objects
        .filter(container_number__icontains=query)
        .values_list("container_number", flat=True)
        .distinct()[:10]
    )

    return JsonResponse({"results": list(containers)})


@login_required
@role_required(["controller", "master"])
def trash(request):
    post_id = request.GET.get("post_id")
    post = get_object_or_404(Post, id=post_id)

    if request.method == "POST":
        vin_code = (request.POST.get("vin_code") or "").strip().upper()
        # поддержим оба имени из формы: comment ИЛИ description
        comment = (request.POST.get("comment") or request.POST.get("description") or "").strip()

        if not vin_code:
            messages.error(request, "❌ Укажите VIN-код.")
            return redirect(f"{reverse('trash')}?post_id={post_id}")

        # 📸 Фото: поддержим оба имени поля — trash_photos и container_photos
        files = request.FILES.getlist("trash_photos") or request.FILES.getlist("container_photos")
        photo_urls = []
        if files:
            folder_rel = "images/trash"
            folder_abs = os.path.join(settings.MEDIA_ROOT, folder_rel)
            os.makedirs(folder_abs, exist_ok=True)

            for f in files:
                _, ext = os.path.splitext(f.name)
                safe_ext = ext.lower() if ext else ".jpg"
                filename = f"photo_{uuid.uuid4().hex}{safe_ext}"
                rel_path = os.path.join(folder_rel, filename)
                abs_path = os.path.join(settings.MEDIA_ROOT, rel_path)

                with open(abs_path, "wb+") as dst:
                    for chunk in f.chunks():
                        dst.write(chunk)

                photo_urls.append(f"{settings.MEDIA_URL}{rel_path}")

        # 🆔 В качестве ключа истории используем VIN
        bucket, _ = ContainerHistory.objects.get_or_create(container_number=vin_code)

        # Пишем запись БЕЗ has_defect
        bucket.add_entry(
            post=post,
            controller_username=request.user.username,
            has_defect=None,                # важно: тогда ключ не попадёт в JSON
            description=comment,
            photos=photo_urls,
            date_added=now_almaty_iso(),
        )

        messages.success(request, "✅ Данные сохранены!")
        return redirect(f"{reverse('trash')}?post_id={post_id}")

    return render(request, "supplies/trash.html", {
        "post_id": post_id,
        "post": post,
    })
