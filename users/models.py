from datetime import time
from datetime import datetime, date
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.auth import get_user_model
from supplies.models import ContainerUnloadingZoneSBInspection
import json
from django.conf import settings


class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('controller', 'Контролер'),
        ('master', 'Мастер'),
        ('head_area', 'Начальник участка'),
        ('admin', 'Администратор'),
        ('qrr_specialist', 'QRR специалист'),
        ('qrr_supervisor', 'QRR начальник участка'),
        ('qrr_shift_lead', 'QRR начальник смены'),
        ('dp', 'Делопроизводитель'),
        ('uud_controller', 'УУД контролер'),                 # ✅ добавлено
        ('uud_master', 'УУД мастер'),                        # ✅ добавлено
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='controller')

    # Обязательные поля
    first_name = models.CharField(max_length=150, verbose_name="Имя")
    last_name = models.CharField(max_length=150, verbose_name="Фамилия")

    # Необязательные поля
    patronymic = models.CharField(max_length=150, verbose_name="Отчество", blank=True, null=True)
    position = models.CharField(max_length=255, verbose_name="Должность", blank=True, null=True)
    email = models.EmailField(verbose_name="E-mail", blank=True, null=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True, verbose_name="Аватар")

    def is_controller(self):
        return self.role == 'controller'

    def is_master(self):
        return self.role == 'master'

    def is_admin(self):
        return self.role == 'admin'

    def is_uud_controller(self):  # ✅ добавлено
        return self.role == 'uud_controller'

    def is_uud_master(self):      # ✅ добавлено
        return self.role == 'uud_master'


    def get_full_name_with_patronymic(self):
        if self.patronymic:
            return f"{self.last_name} {self.first_name} {self.patronymic}"
        return f"{self.last_name} {self.first_name}"

    class Meta:
        permissions = [
            ("access_to_the_master_dashboard", "Доступ к панели мастера"),
            ("access_to_dp_rvd", "Доступ к РВД делопроизводителю"),
            ("access_to_post_of_the_controller", "Доступ к постам контролера"),
            ("access_to_the_uud_table", 'Доступ к таблице УУД'),
            ("access_to_the_marriage_table", "Доступ к таблице женитьбы"),
            ("access_to_the_qrr_responsible", "Доступ к сайту QRR для ответственных"),
            ("access_to_the_guide", "Доступ к справочнику"),
            ("access_to_the_shift_management", "Доступ к управлению сменой"),
            ("access_to_the_rvd", "Доступ к РВД"),
            ("access_to_the_vqa_data_management", "Доступ к сайту для управления данными VQA"),
            ("access_to_the_qrqc_report_vqa", "Доступ к QRQC отчету VQA"),
            ("access_to_tracking_by_vin", "Доступ к отслеживанию по VIN"),
            ("access_to_pqa_data", "Доступ к данным PQA"),
            ("access_to_vqa_data", "Доступ к данным VQA"),
            ("access_to_indicators", "Доступ к показателям"),
            ("access_to_body_shop_data", "Доступ к данным Body Shop"),

            ('show_buttons_to_fi_posts_for_controllers', "Показ постов первой инспекции контролерам"),
            ('show_buttons_for_vqa_controllers', "Показ кнопок для контролеров VQA"),
            ('show_button_counter_changan', 'Показ кнопки TRIM IN Changan'),
            ('show_button_counter_chery', 'Показ кнопки TRIM IN Chery'),
            ('show_button_counter_gwm', 'Показ кнопки TRIM IN GWM'),
            ('show_button_counter_frame', 'Показ кнопки TRIM IN Frame'),
            ('show_button_counter_trim_out_changan', 'Показ кнопки TRIM OUT Changan'),
            ('show_button_counter_trim_out_chery', 'Показ кнопки TRIM OUT Chery'),
            ('show_button_counter_trim_out_gwm', 'Показ кнопки TRIM OUT GWM'),
            ('show_button_counter_trim_out_frame', 'Показ кнопки TRIM OUT Frame'),
        ]



User = get_user_model()


class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    defect = models.ForeignKey(ContainerUnloadingZoneSBInspection, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    vin_number = models.CharField(max_length=50, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def mark_as_read(self):
        self.is_read = True
        self.save()

    def __str__(self):
        return f"{self.recipient.username}: {'[Прочитано]' if self.is_read else '[Непрочитано]'} {self.message[:50]}"


class HelpdeskContact(models.Model):
    position = models.CharField(max_length=255, verbose_name="Должность")
    employee_name = models.CharField(max_length=255, verbose_name="Сотрудник")
    phone_number = models.CharField(max_length=50, verbose_name="Мобильный")
    email = models.EmailField(verbose_name="E-mail", blank=True, null=True)
    department = models.CharField(max_length=255, verbose_name="Отдел")

    def __str__(self):
        return f"{self.employee_name} ({self.position})"

    class Meta:
        verbose_name = "Контакт справочного отдела"
        verbose_name_plural = "Контакты справочного отдела"


class Employee(models.Model):
    name = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    department = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.position} ({self.department or 'Нет отдела'})"

    class Meta:
        ordering = ['name']


class Selection(models.Model):
    manager = models.ForeignKey(User, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    selected_date = models.DateField()
    is_xtk = models.BooleanField(default=False, verbose_name="ХТК")
    hours = models.PositiveIntegerField(default=8, verbose_name="Часы")
    justification = models.TextField("Обоснование", blank=True, null=True)
    start_time = models.TimeField(verbose_name="Начало работы", default=time(7, 30))
    end_time = models.TimeField(verbose_name="Окончание работы", default=time(16, 30))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.start_time >= self.end_time:
            from django.core.exceptions import ValidationError
            raise ValidationError("Время начала должно быть раньше окончания")

        delta = datetime.combine(date.min, self.end_time) - datetime.combine(date.min, self.start_time)
        hours = delta.total_seconds() // 3600
        self.hours = int(hours - 1) if hours >= 8 else int(hours)

        super().save(*args, **kwargs)

        OvertimeRecord.objects.update_or_create(
            employee=self.employee,
            date=self.selected_date,
            defaults={
                'start_time': self.start_time,
                'end_time': self.end_time,
                'hours': self.hours,
                'justification': self.justification,
                'is_xtk': self.is_xtk,
                'added_by': self.manager,
            }
        )

    def __str__(self):
        return f"{self.employee.name} selected by {self.manager.username} on {self.selected_date}"

    class Meta:
        ordering = ['-selected_date']
        unique_together = ('manager', 'employee', 'selected_date')


class OvertimeRecord(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    start_time = models.TimeField(default=time(7, 30))
    end_time = models.TimeField(default=time(16, 30))
    hours = models.PositiveIntegerField(default=8)
    justification = models.TextField("Обоснование", blank=True, null=True)
    is_xtk = models.BooleanField(default=False, verbose_name="ХТК")
    added_by = models.ForeignKey(User, on_delete=models.CASCADE)

    compensated_day = models.DateField(
        blank=True,
        null=True,
        verbose_name="День отгула (за переработку)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('employee', 'date')  # ❗ Чтобы не было дублей
        ordering = ['-date']

    def save(self, *args, **kwargs):
        # Расчёт часов (с учётом перерыва)
        if self.start_time >= self.end_time:
            from django.core.exceptions import ValidationError
            raise ValidationError("Время начала должно быть раньше окончания")
        delta = datetime.combine(date.min, self.end_time) - datetime.combine(date.min, self.start_time)
        hours = delta.total_seconds() // 3600
        self.hours = int(hours - 1) if hours >= 8 else int(hours)
        super().save(*args, **kwargs)


class ExportHistory(models.Model):
    manager = models.ForeignKey(User, on_delete=models.CASCADE)
    file_name = models.CharField(max_length=255)
    export_date = models.DateTimeField(auto_now_add=True)
    record_count = models.IntegerField()
    export_data = models.JSONField(default=list, null=True, blank=True)

    def __str__(self):
        return f"{self.file_name} exported by {self.manager.username} on {self.export_date.strftime('%d.%m.%Y %H:%M')}"

    class Meta:
        ordering = ['-export_date']
        verbose_name_plural = 'История экспортов'

    def get_data_as_list(self):
        try:
            if isinstance(self.export_data, str):
                return json.loads(self.export_data)
            return self.export_data or []
        except Exception as e:
            print(f"Ошибка в get_data_as_list: {str(e)}")
            return []


class KTVDefect(models.Model):
    TABLE_CHOICES = [
        ("by_grades", "По грейдам"),
        ("by_mass", "По массовости"),
    ]

    table_type = models.CharField(
        max_length=20,
        choices=TABLE_CHOICES,
        verbose_name="Источник таблицы"
    )
    detail = models.CharField(max_length=255, verbose_name="Деталь")
    defect = models.CharField(max_length=255, verbose_name="Дефект")
    grade = models.CharField(max_length=50, verbose_name="Грейд", blank=True, null=True)
    count = models.PositiveIntegerField(default=0, verbose_name="Количество")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата записи")
    visible_from = models.DateField(verbose_name="Показать с даты")
    comment = models.TextField(blank=True, null=True, verbose_name="Комментарий")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ktv_defects",
        verbose_name="Кто отложил"
    )

    class Meta:
        verbose_name = "Отложенный дефект (KTV)"
        verbose_name_plural = "Отложенные дефекты (KTV)"

    def __str__(self):
        return f"{self.detail} — {self.defect} ({self.table_type})"

