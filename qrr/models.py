from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class QRRInvestigation(models.Model):
    # Связь с дефектом
    vin_history = models.ForeignKey("vehicle_history.VINHistory", on_delete=models.CASCADE, related_name="investigations")

    # Автор и подтверждающие лица
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_investigations")
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="submitted_investigations")

    # Номер формы, даты, время
    form_number = models.CharField(max_length=20, unique=True)  # пример: 2025-04-001
    form_date = models.DateField(null=True, blank=True, verbose_name="Дата заполнения формы")  # 1.4
    form_time = models.TimeField(null=True, blank=True, verbose_name="Время заполнения формы")  # 1.5
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    # Выполнил / Подтвердил (как пользователь и как текст)
    performed_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performed_qrr",
        limit_choices_to={'role__in': ['qrr_specialist', 'qrr_supervisor', 'qrr_shift_lead']},
        verbose_name="Выполнил (из пользователей)"
    )
    performed_by_name = models.CharField(max_length=100, blank=True, verbose_name="Выполнил (вручную)")

    confirmed_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_qrr",
        limit_choices_to={'role__in': ['qrr_supervisor', 'qrr_shift_lead']},
        verbose_name="Подтвердил (из пользователей)"
    )
    confirmed_by_name = models.CharField(max_length=100, blank=True, verbose_name="Подтвердил (вручную)")

    shift = models.CharField(max_length=20, choices=[("day", "Дневная"), ("night", "Ночная")])  # 1.7
    inspector = models.CharField(max_length=100)  # 1.6
    confirmed_tl_sv = models.CharField(max_length=100, blank=True)  # 1.8

    # Машина и дефект
    brand = models.CharField(max_length=100)  # 1.9
    model = models.CharField(max_length=100)  # 2.0
    station = models.CharField(max_length=100)  # 2.1
    vin = models.CharField(max_length=50)  # 2.2
    grade = models.CharField(max_length=10)  # 2.3
    defect_text = models.TextField()  # 2.4
    inspection_standard = models.TextField(blank=True)  # 2.5
    check_method = models.CharField(max_length=255, blank=True)  # 2.6
    value = models.CharField(max_length=100, blank=True)  # 2.7
    standard_criteria = models.TextField(blank=True)  # 2.8
    qtf_nominal = models.CharField(max_length=100, blank=True)  # 2.9
    defect_description = models.TextField(blank=True)  # 3.0
    defect_photo = models.ImageField(upload_to='qrr/defects/', null=True, blank=True)  # 3.1
    repair_method = models.TextField(blank=True)  # 3.2

    # Анализ текущего состояния
    car_checked_count = models.PositiveIntegerField(null=True, blank=True)  # 3.3
    ng_count = models.PositiveIntegerField(null=True, blank=True)  # 3.4
    checklist_number = models.CharField(max_length=100, blank=True)  # 3.5

    # Временная мера, вывод
    temporary_measure = models.TextField(blank=True)  # 5.1
    department = models.CharField(max_length=100, blank=True)  # 5.2
    conclusion = models.TextField(blank=True)  # 5.3

    # CRCR и KTM
    crcr_number = models.CharField(max_length=100, blank=True)  # 5.7
    ktm_number = models.CharField(max_length=100, blank=True)  # 5.8

    # Статус
    status = models.CharField(max_length=20, choices=[
        ('draft', 'Черновик'),
        ('in_progress', 'В процессе'),
        ('completed', 'Завершено')
    ], default='draft')

    def __str__(self):
        return f"БРД {self.form_number} - {self.vin}"


class InvestigationFactor(models.Model):
    investigation = models.ForeignKey(QRRInvestigation, on_delete=models.CASCADE, related_name="factors")
    category = models.CharField(max_length=50)  # человек, материал и т.д.
    description = models.TextField()


class FactorCheck(models.Model):
    investigation = models.ForeignKey(QRRInvestigation, on_delete=models.CASCADE, related_name="factor_checks")
    factor_text = models.CharField(max_length=255)
    check_method = models.CharField(max_length=255)
    responsible = models.CharField(max_length=100)
    date = models.DateField()
    comment = models.TextField(blank=True)
    attachment = models.FileField(upload_to='qrr/factor_checks/', null=True, blank=True)
    result = models.CharField(max_length=2, choices=[('OK', 'ОК'), ('NG', 'NG')])
    factor_type = models.CharField(max_length=100, blank=True)  # основной / вспомогательный


class InvestigationRequest(models.Model):
    investigation = models.ForeignKey(QRRInvestigation, on_delete=models.CASCADE, related_name="requests")
    factor = models.CharField(max_length=100)
    action = models.TextField()
    responsible = models.CharField(max_length=100)
    date = models.DateField()
    result = models.TextField()


class InvestigationResponsibility(models.Model):
    investigation = models.ForeignKey(QRRInvestigation, on_delete=models.CASCADE, related_name="responsibilities")
    factor = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    full_name = models.CharField(max_length=100)
    crcr_number = models.CharField(max_length=100, blank=True)
    ktm_number = models.CharField(max_length=100, blank=True)
    comment = models.TextField(blank=True)


class QRRResponsible(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Ответственный")

    class Meta:
        verbose_name = "Ответственный (QRR)"
        verbose_name_plural = "Ответственные (QRR)"

    def __str__(self):
        return self.name


