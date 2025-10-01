from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower


class PostAssembly(models.Model):
    """Модель поста в цехе сборки"""
    name = models.CharField(max_length=100, unique=True, verbose_name="Название поста (сборка)")
    location = models.CharField(max_length=200, blank=True, null=True, verbose_name="Местоположение (сборка)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Пост (сборка)"
        verbose_name_plural = "Посты (сборка)"


class DefectAssembly(models.Model):
    """Модель для хранения дефектов на сборке"""
    name = models.CharField(max_length=255, unique=True, verbose_name="Название дефекта (сборка)")
    posts = models.ManyToManyField(PostAssembly, related_name="defects", verbose_name="Посты (сборка)")  # ✅ Связь с PostAssembly

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Дефект (сборка)"
        verbose_name_plural = "Дефекты (сборка)"


class AssemblyPart(models.Model):
    MODIFICATION_CHOICES = [
        ('2WD', '2WD'),
        ('4WD', '4WD'),
    ]

    name = models.CharField(max_length=255, verbose_name="Название узла/детали")
    modification = models.CharField(max_length=3, choices=MODIFICATION_CHOICES, verbose_name="Модификация", default='2WD')  # ✅ Добавлено
    size = models.CharField(max_length=50, verbose_name="Размер")

    # ✅ Диапазон количества (например, 4-6)
    min_quantity = models.IntegerField(verbose_name="Минимальное количество", blank=True, null=True)
    max_quantity = models.IntegerField(verbose_name="Максимальное количество", blank=True, null=True)

    # ✅ Диапазон момента затяжки (например, 42–54 Н·м)
    min_torque = models.FloatField(verbose_name="Минимальный момент затяжки (Нм)", blank=True, null=True)
    max_torque = models.FloatField(verbose_name="Максимальный момент затяжки (Нм)", blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.modification})"

    class Meta:
        verbose_name = "Узел/Деталь (сборка)"
        verbose_name_plural = "Узлы/Детали (сборка)"


class AssemblyDefect(models.Model):
    """Справочник дефектов для сборки"""
    name = models.CharField(max_length=255, unique=True, verbose_name="Название дефекта (сборка)")
    nameENG = models.CharField(max_length=255, blank=True, null=True, verbose_name="Defect name (ENG)")
    posts = models.ManyToManyField("PostAssembly", related_name="assembly_defects", blank=True, verbose_name="Посты")  # ✅

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Дефект (справочник сборка)"
        verbose_name_plural = "Дефекты (справочник сборка)"


class AssemblyZone(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Название зоны")
    posts = models.ManyToManyField("PostAssembly", related_name="assembly_zones", blank=True, verbose_name="Посты")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Подсистема (зона сборки)"
        verbose_name_plural = "Подсистемы сборки"


class AssemblyUnit(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название узла (сборка)")  # ⬅️ убрали unique=True
    zone = models.ForeignKey('AssemblyZone', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Зона/группа узла")
    posts = models.ManyToManyField("PostAssembly", related_name="assembly_units", blank=True, verbose_name="Посты")

    def __str__(self):
        return f"{self.name} ({self.zone})"

    class Meta:
        verbose_name = "Детали (сборка)"
        verbose_name_plural = "Детали(сборка)"
        # Уникальность имени внутри зоны (регистронезависимо)
        constraints = [
            UniqueConstraint(Lower('name'), 'zone', name='uniq_unit_name_per_zone_ci')
        ]


class AssemblyDefectGrade(models.Model):
    """Грейды дефектов для сборки"""
    name = models.CharField(max_length=50, unique=True, verbose_name="Грейд дефекта (сборка)")
    description = models.TextField(blank=True, null=True, verbose_name="Описание грейда (сборка)")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Грейд дефекта (сборка)"
        verbose_name_plural = "Грейды дефектов (сборка)"


class AssemblyDefectResponsible(models.Model):
    """Ответственные за дефекты (сборка)"""
    name = models.CharField(max_length=100, unique=True, verbose_name="Ответственный за дефект (сборка)")
    department = models.CharField(max_length=100, blank=True, null=True, verbose_name="Цех / Отдел (сборка)")
    posts = models.ManyToManyField(PostAssembly, related_name="defect_responsibles_assembly", verbose_name="Посты (сборка)")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Ответственный за дефект (сборка)"
        verbose_name_plural = "Ответственные за дефекты (сборка)"



