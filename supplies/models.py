from django.db import models
from django.conf import settings
import os
from django.utils.timezone import now


class TraceData(models.Model):
    """Модель для хранения данных из трейсинга"""
    brand = models.CharField(max_length=50, verbose_name="Brand", default="Unknown")
    model = models.CharField(max_length=50, verbose_name="Model", default="Unknown")
    config_code = models.CharField(max_length=50, verbose_name="Configuration Code")
    body_number = models.CharField(max_length=50, verbose_name="Body Number")
    vin_rk = models.CharField(max_length=50, unique=True, verbose_name="VIN RK")
    vin_c = models.CharField(max_length=50, verbose_name="VIN C")
    engine_number = models.CharField(max_length=50, verbose_name="Engine Number")
    engine_volume = models.IntegerField(verbose_name="Engine Volume")
    modification = models.CharField(max_length=50, verbose_name="Modification")
    body_color = models.CharField(max_length=50, verbose_name="Body Color")
    transmission = models.CharField(max_length=50, verbose_name="Transmission")
    engine_power = models.CharField(max_length=50, verbose_name="Engine Power (hp/kW)")
    gross_weight = models.IntegerField(verbose_name="Gross Weight")
    weight = models.IntegerField(verbose_name="Weight")
    config_code_extra = models.CharField(max_length=50, verbose_name="Additional Configuration Code")
    color_1c = models.CharField(max_length=50, verbose_name="Color in 1C")
    body_type = models.CharField(max_length=50, verbose_name="Body Type")
    seat_capacity = models.IntegerField(verbose_name="Seating Capacity")
    production_year = models.IntegerField(verbose_name="Production Year")

    # 🔹 Новый столбец
    interior_color = models.CharField(
        max_length=50,
        verbose_name="Interior Color",
        blank=True,
        null=True
    )

    # 🔹 Новые поля
    tdmm_front_axle = models.IntegerField(
        verbose_name="ТДММ на переднюю ось (кг)",
        blank=True,
        null=True
    )
    tdmm_rear_axle = models.IntegerField(
        verbose_name="ТДММ на заднюю ось (кг)",
        blank=True,
        null=True
    )
    butch_number = models.CharField(
        max_length=100,
        verbose_name="Номер батча",
        blank=True,
        null=True
    )

    date_added = models.DateTimeField(default=now, verbose_name="Date Added")

    class Meta:
        verbose_name = "Trace Data"
        verbose_name_plural = "Trace Data"

    def __str__(self):
        return f"VIN: {self.vin_rk} - Engine: {self.engine_number}"



# Функции для сохранения изображений в определенные папки
def container_image_path(instance, filename):
    return os.path.join("images/containers", f"container_{instance.id}_{filename}")


def pallet_image_path(instance, filename):
    return os.path.join("images/pallets", f"pallet_{instance.id}_{filename}")


def defect_image_path(instance, filename):
    return os.path.join("images/defects", f"defect_{instance.id}_{filename}")


class Post(models.Model):
    """Модель поста"""
    name = models.CharField(max_length=100, unique=True, verbose_name="Название поста")
    location = models.CharField(max_length=200, blank=True, null=True, verbose_name="Местоположение")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Пост"
        verbose_name_plural = "Посты"


class Detail(models.Model):
    """Модель для хранения деталей"""
    name = models.CharField(max_length=255, unique=True, verbose_name="Название детали")
    posts = models.ManyToManyField(Post, related_name="details", verbose_name="Посты")  # ✅ Связь с новым Post

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Деталь"
        verbose_name_plural = "Детали"


class Defect(models.Model):
    """Модель для хранения дефектов"""
    name = models.CharField(max_length=255, unique=True, verbose_name="Название дефекта")
    posts = models.ManyToManyField(Post, related_name="defects", verbose_name="Посты")  # ✅ Связь с новым Post

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Дефект"
        verbose_name_plural = "Дефекты"


class DefectGrade(models.Model):
    """Модель для хранения грейдов дефектов"""
    name = models.CharField(max_length=50, unique=True, verbose_name="Грейд дефекта")
    description = models.TextField(blank=True, null=True, verbose_name="Описание грейда")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Грейд дефекта"
        verbose_name_plural = "Грейды дефектов"


class DefectResponsible(models.Model):
    """Модель для хранения ответственных за дефекты"""
    name = models.CharField(max_length=100, unique=True, verbose_name="Ответственный за дефект")
    department = models.CharField(max_length=100, blank=True, null=True, verbose_name="Цех / Отдел")
    posts = models.ManyToManyField(Post, related_name="defect_responsibles", verbose_name="Посты")  # ✅ Привязка к посту

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Ответственный за дефект"
        verbose_name_plural = "Ответственные за дефекты"


class ContainerUnloadingZone2Inspection(models.Model):
    """Зона выгрузки контейнеров, этаж 2 (модель инспекции с возможностью загрузки нескольких фото дефектов)"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, verbose_name="Пост")
    controller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Контроллер")

    container_number = models.CharField(max_length=20, verbose_name="Номер контейнера")
    pallet_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="Номер палета")

    detail = models.ForeignKey(Detail, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Деталь")
    defect = models.ForeignKey(Defect, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Дефект")

    defect_description = models.CharField(max_length=100, blank=True, null=True, verbose_name="Описание дефекта")

    container_image = models.ImageField(
        upload_to="images/containers/",
        blank=True, null=True,
        verbose_name="Фото контейнера"
    )

    pallet_image = models.ImageField(
        upload_to="images/pallets/",
        blank=True, null=True,
        verbose_name="Фото палета"
    )

    defect_images = models.TextField(
        blank=True, null=True,
        verbose_name="Фото дефекта (список URL через запятую)"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата фиксации")

    def __str__(self):
        return f"Дефект на {self.post.name} ({self.container_number})"

    def get_defect_images(self):
        """Возвращает список путей к изображениям"""
        return self.defect_images.split(", ") if self.defect_images else []

    def add_defect_image(self, image_url):
        """Добавляет новый URL изображения к полю defect_images"""
        images = self.get_defect_images()
        images.append(image_url)
        self.defect_images = ", ".join(images)
        self.save()

    class Meta:
        verbose_name = "Зона выгрузки контейнеров, этаж 2 (Инспекция)"
        verbose_name_plural = "Зона выгрузки контейнеров, этаж 2 (Инспекции)"


class ContainerUnloadingZoneSBInspection(models.Model):
    """Зона выгрузки контейнеров SB (инспекция с возможностью загрузки нескольких фото контейнера)"""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, verbose_name="Пост")
    controller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Контроллер"
    )

    container_number = models.CharField(max_length=20, verbose_name="Номер контейнера")

    container_images = models.TextField(
        blank=True, null=True,
        verbose_name="Фото контейнера (список URL через запятую)"
    )

    container_number_image = models.ImageField(
        upload_to="images/container_numbers/",
        blank=True, null=True,
        verbose_name="Фото номера контейнера"
    )

    container_description = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="Описание контейнера"
    )

    seal_image = models.ImageField(
        upload_to="images/container_seals/",
        blank=True, null=True,
        verbose_name="Фото пломбы контейнера"
    )

    seal_description = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="Описание пломбы"
    )

    CONTAINER_STATUS_CHOICES = [
        ('damaged', 'Контейнер поврежден'),
        ('not_damaged', 'Контейнер не поврежден')
    ]

    container_status = models.CharField(
        max_length=20, choices=CONTAINER_STATUS_CHOICES,
        verbose_name="Состояние контейнера"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата фиксации")

    def __str__(self):
        return f"Инспекция контейнера {self.container_number}"

    def get_container_images(self):
        """Возвращает список путей к изображениям контейнера"""
        return self.container_images.split(", ") if self.container_images else []

    def add_container_image(self, image_url):
        """Добавляет новый URL изображения к полю container_images"""
        images = self.get_container_images()
        images.append(image_url)
        self.container_images = ", ".join(images)
        self.save()

    class Meta:
        verbose_name = "Зона выгрузки контейнеров SB (Инспекция)"
        verbose_name_plural = "Зона выгрузки контейнеров SB (Инспекции)"


class BodyDetail(models.Model):
    """Детали кузова и интерьера, сгруппированные по части машины"""

    ZONE_CHOICES = [
        # Экстерьер
        ("left", "Левая сторона"),
        ("right", "Правая сторона"),
        ("front", "Передняя часть"),
        ("back", "Задняя часть"),
        ("up", "Верх"),
        ("all", "Все зоны (Прочее)"),

        # Интерьер (новые)
        ("mult", "Мультимедиа"),
        ("salon", "Салон"),
        ("fd_right", "Дверь передняя правая"),
        ("fd_left", "Дверь передняя левая"),
        ("bd_right", "Дверь задняя правая"),
        ("bd_left", "Дверь задняя левая"),
    ]

    name = models.CharField(max_length=255, unique=True, verbose_name="Название детали")
    zone = models.CharField(
        max_length=20,  # 🔥 увеличил с 10 до 20 символов, чтобы влезли новые значения типа "fd_right"
        choices=ZONE_CHOICES,
        verbose_name="Часть кузова/интерьера"
    )
    posts = models.ManyToManyField(
        "Post",
        related_name="body_details",
        verbose_name="Посты"
    )

    def str(self):
        return f"{self.name} ({self.get_zone_display()})"

    class Meta:
        verbose_name = "Деталь кузова/интерьера"
        verbose_name_plural = "Детали кузова и интерьера"
