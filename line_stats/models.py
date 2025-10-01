from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

# === Общие константы ===
FINAL_POSTS = (
    "Финал текущий контроль",
)

LINES = (
    ("gwm", "GWM"),
    ("chery", "CHERY"),
    ("changan", "CHANGAN"),
    ("frame", "FRAME LINE"),
    ("pdi", "PDI"),
)

# --- Смены и их интервалы ---
SHIFT_CHOICES = (
    ("s1", _("Первая смена")),
    ("s2", _("Вторая смена")),
)

SHIFTS = {
    # Первая смена (по ТЗ)
    "s1": (
        ("07:30", "08:30"),
        ("08:30", "09:30"),
        ("09:30", "09:40"),
        ("09:40", "10:30"),
        ("10:30", "11:30"),
        ("11:30", "12:10"),
        ("12:10", "12:50"),
        ("12:50", "13:30"),
        ("13:30", "14:30"),
        ("14:30", "14:40"),
        ("14:40", "15:30"),
        ("15:30", "16:30"),
    ),
    # Вторая смена (пересекает полночь)
    "s2": (
        ("16:30", "17:30"),
        ("17:30", "18:30"),
        ("18:30", "18:40"),
        ("18:40", "19:30"),
        ("19:30", "20:20"),
        ("20:20", "21:00"),
        ("21:00", "22:00"),
        ("22:00", "23:00"),
        ("23:00", "23:10"),
        ("23:10", "00:00"),
        ("00:00", "01:00"),
        ("01:00", "01:30"),
    ),
}

def get_slots(shift: str = "s1"):
    """Вернуть кортеж интервалов для смены (по умолчанию S1)."""
    return SHIFTS.get(shift or "s1", SHIFTS["s1"])


def slot_label(start: "models.TimeField", end: "models.TimeField") -> str:
    return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"


class EditorsWhitelist(models.Model):
    """Список пользователей, которые могут править факт/план через UI.
    Просто добавляем сюда ровно трёх человек.
    """
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="line_stats_editors")

    class Meta:
        verbose_name = _("Допущенные редакторы")
        verbose_name_plural = _("Допущенные редакторы")

    def __str__(self):
        return f"Editors: {self.users.count()}"


class HourlyPlan(models.Model):
    """План на слот времени с версионированием по дате.

    Принцип: план хранится с полем effective_from (дата начала действия).
    Если завтра план изменили, мы НЕ переписываем прошлые записи, а создаём новую
    строку с новой датой. В уже сохранённых фактах будет храниться снимок плана.
    """
    line = models.CharField(max_length=16, choices=LINES, db_index=True)
    shift = models.CharField(max_length=2, choices=SHIFT_CHOICES, default="s1", db_index=True)
    start = models.TimeField(db_index=True)
    end = models.TimeField(db_index=True)
    effective_from = models.DateField(db_index=True, help_text=_("Дата, с которой этот план действует"))
    value = models.PositiveIntegerField(default=0, help_text=_("Сколько машин должно пройти в этот час"))

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = _("План по часу")
        verbose_name_plural = _("Планы по часам")
        # Для одной линии и слота времени не должно быть двух планов с одинаковым effective_from
        unique_together = ("line", "shift", "start", "end", "effective_from")
        ordering = ("line", "shift", "start", "-effective_from")

    def __str__(self):
        return f"{self.line} {self.shift} {slot_label(self.start, self.end)} plan={self.value} from {self.effective_from}"

    @classmethod
    def resolve_for(cls, *, date, line: str, start, end, shift: str = "s1"):
        """Найти актуальный план для конкретной даты/линии/слота.
        Выбираем запись с максимальным effective_from <= date.
        Возвращаем int или 0, если не найдено.
        """
        obj = (
            cls.objects.filter(line=line, shift=shift, start=start, end=end, effective_from__lte=date)
            .order_by("-effective_from")
            .first()
        )
        return obj.value if obj else 0


class HourlyLineStat(models.Model):
    """Факт по финальному посту за час (снимок плана).

    Важно: план здесь хранится как snapshot (plan_snapshot). Если позже план
    поменяют, эта запись НЕ изменится.
    """
    date = models.DateField(db_index=True)
    line = models.CharField(max_length=16, choices=LINES, db_index=True)
    shift = models.CharField(max_length=2, choices=SHIFT_CHOICES, default="s1", db_index=True)
    start = models.TimeField(db_index=True)
    end = models.TimeField(db_index=True)

    # Снимок плана и фактическое значение
    plan_snapshot = models.PositiveIntegerField(default=0)
    actual = models.PositiveIntegerField(default=0)

    downtime_min = models.PositiveIntegerField(default=0)
    downtime_reason = models.CharField(max_length=500, blank=True)
    # Кто внёс причину простоя (ответственный по линии)
    reason_author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="line_stats_reason_authors",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = _("Факт по часу (финал)")
        verbose_name_plural = _("Факты по часам (финал)")
        unique_together = ("date", "line", "shift", "start", "end")
        ordering = ("date", "line", "shift", "start")

    def __str__(self):
        return f"{self.date} {self.line} {self.shift} {slot_label(self.start, self.end)} fact={self.actual} plan={self.plan_snapshot}"

    @property
    def slot_label(self):
        return slot_label(self.start, self.end)

    def apply_plan_snapshot_if_empty(self):
        """Если план в записи пуст, захватываем актуальный на дату записи."""
        if not self.plan_snapshot:
            self.plan_snapshot = HourlyPlan.resolve_for(
                date=self.date, line=self.line, start=self.start, end=self.end, shift=self.shift
            )


# === Почасовая статистика PDI ===
class HourlyPDIStat(models.Model):
    """Почасовая статистика PDI: вход/выход/в ремонте.

    В ремонте (wip) — сколько машин находятся в PDI на конец часа.
    """
    date = models.DateField(db_index=True)
    shift = models.CharField(max_length=2, choices=SHIFT_CHOICES, default="s1", db_index=True)
    start = models.TimeField(db_index=True)
    end = models.TimeField(db_index=True)

    in_count = models.PositiveIntegerField(default=0, help_text=_("Сколько машин вошло в PDI за час"))
    out_count = models.PositiveIntegerField(default=0, help_text=_("Сколько машин вышло из PDI за час"))
    wip_count = models.PositiveIntegerField(default=0, help_text=_("Сколько машин находятся в PDI на конец часа"))

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = _("Статистика PDI по часу")
        verbose_name_plural = _("Статистика PDI по часам")
        unique_together = ("date", "shift", "start", "end")
        ordering = ("date", "shift", "start")

    def __str__(self):
        return f"PDI {self.date} {self.shift} {self.start.strftime('%H:%M')}-{self.end.strftime('%H:%M')} in={self.in_count} out={self.out_count} wip={self.wip_count}"
