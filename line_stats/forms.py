

from __future__ import annotations
from typing import Iterable, List, Tuple

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Модели line_stats
from line_stats.models import (
    HourlyPlan,
    HourlyLineStat,
    HourlyPDIStat,
    EditorsWhitelist,
    SHIFT_CHOICES,
    get_slots,
)

# Доступные «линии» для таблицы (4 производственные + отдельный PDI)
LINE_CHOICES = (
    ("gwm", "GWM"),
    ("frame", "GWM FRAME LINE"),
    ("chery", "CHERY"),
    ("changan", "CHANGAN"),
    ("pdi", "PDI"),  # особый режим отображения
)


# === Общие фильтры дня/линии/смены ===
class DailyParamsForm(forms.Form):
    date = forms.DateField(label=_("Дата"))
    line = forms.ChoiceField(choices=LINE_CHOICES, label=_("Линия"))
    shift = forms.ChoiceField(choices=SHIFT_CHOICES, initial="s1", label=_("Смена"))


# === План (создание новой версии с effective_from) — для директоров ===
class PlanEditorForm(forms.ModelForm):
    class Meta:
        model = HourlyPlan
        fields = ("line", "shift", "start", "end", "effective_from", "value")
        labels = {
            "line": _("Линия"),
            "shift": _("Смена"),
            "start": _("Начало"),
            "end": _("Конец"),
            "effective_from": _("Действует с даты"),
            "value": _("План, шт/час"),
        }


# === Ввод причины простоя по слотам — для начальников участков ===
class ReasonPerSlotForm(forms.Form):
    """Форма одной строки-слота. Факт/план/простой вычисляются вне формы.
    Пользователь вводит только причину.
    """
    start = forms.TimeField(widget=forms.HiddenInput)
    end = forms.TimeField(widget=forms.HiddenInput)
    downtime_reason = forms.CharField(
        required=False,
        label=_("Причина простоя"),
        widget=forms.TextInput(attrs={"placeholder": _("Причина простоя (опционально)")}),
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        # Если причина заполнена, проверяем, что пользователь допущен как редактор причин
        if cleaned.get("downtime_reason"):
            if not self.user or not EditorsWhitelist.objects.filter(users=self.user).exists():
                raise ValidationError(_("У вас нет прав вносить причину простоя."))
        return cleaned


def make_reason_formset(slots: Iterable[Tuple[str, str]], *, user=None):
    """Создать FormSet для всех слотов смены с предзаполненными start/end.
    `slots` — последовательность пар ("HH:MM","HH:MM").
    """
    base = forms.formsets.formset_factory(ReasonPerSlotForm, extra=0)

    class _FS(base):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("initial", [
                {"start": s, "end": e, "downtime_reason": ""} for s, e in slots
            ])
            super().__init__(*args, **kwargs)
            # прокидываем user во все формы
            for f in self.forms:
                f.user = user

    return _FS


# === PDI фильтр (данные только на просмотр) ===
class PDIDailyParamsForm(forms.Form):
    date = forms.DateField(label=_("Дата"))
    shift = forms.ChoiceField(choices=SHIFT_CHOICES, initial="s1", label=_("Смена"))