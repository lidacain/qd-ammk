from django import forms
from .models import AssemblyPart, DefectAssembly


class TorqueControlForm(forms.Form):
    """
    Форма контроля затяжки (DKD).
    """

    vin_number = forms.CharField(
        label="VIN номер",
        max_length=17,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите VIN"}),
    )

    modification = forms.ChoiceField(
        choices=[("2WD", "2WD"), ("4WD", "4WD")],
        label="Тип привода",
        required=True,
        widget=forms.Select(attrs={"class": "form-control", "id": "modification_select"}),
    )

    assembly_part = forms.ModelChoiceField(
        queryset=AssemblyPart.objects.all(),  # ✅ Базовое заполнение, обновляется динамически
        label="Узел / Деталь",
        required=True,
        widget=forms.Select(attrs={"class": "form-control", "id": "assembly_part_select"}),
    )

    torque_values = forms.CharField(
        label="Моменты затяжки",
        required=True,
        widget=forms.HiddenInput(),  # Значения затяжки передаются в виде JSON
    )

    has_defect = forms.ChoiceField(
        choices=[("no", "Дефекта нет"), ("yes", "Есть дефект")],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        required=True
    )

    defect_type = forms.ChoiceField(
        label="Тип дефекта",
        choices=[
            ("", "Выберите тип дефекта"),
            ("under_torque", "Недотяг"),
            ("over_torque", "Перетяг"),
            ("thread_damage", "Резьба сорвана"),
            ("missing", "Отсутствует"),
        ],
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "defect_type_select"}),
    )

    defect_quantity = forms.IntegerField(
        label="Количество",
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Введите количество"}),
    )

    defect_photos = forms.FileField(
        label="Фото дефектов",
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),  # ✅ Исправлено
    )

    def __init__(self, *args, **kwargs):
        """✅ Динамическое обновление узлов/деталей по `modification`"""
        modification = kwargs.pop("modification", None)
        super().__init__(*args, **kwargs)

        # ✅ Обновление узлов/деталей по `modification`
        if modification:
            self.fields["assembly_part"].queryset = AssemblyPart.objects.filter(modification=modification)
        self.fields["assembly_part"].empty_label = "Выберите узел / деталь"

        # ✅ Скрываем поля дефекта, если `has_defect=no`
        if self.data.get("has_defect") == "no":
            self.fields["defect_type"].required = False
            self.fields["defect_quantity"].required = False
            self.fields["defect_photos"].required = False

    def clean_defect_photos(self):
        """✅ Исправленный обработчик загрузки дефектных фото"""
        files = self.files.getlist("defect_photos")
        return files if files else None

    def clean_torque_values(self):
        """✅ Проверка формата переданных значений момента затяжки"""
        import json
        data = self.cleaned_data["torque_values"]
        try:
            values = json.loads(data)
            if not isinstance(values, list):
                raise forms.ValidationError("Моменты затяжки должны быть в формате списка.")
            return values
        except json.JSONDecodeError:
            raise forms.ValidationError("Ошибка формата JSON в моментах затяжки.")


class TorqueGraphForm(forms.Form):
    assembly_part = forms.ModelChoiceField(
        queryset=AssemblyPart.objects.all(),
        label="Узел/деталь",
        widget=forms.Select(attrs={"class": "form-control"})
    )
    start_date = forms.DateField(
        label="Дата начала",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )
    end_date = forms.DateField(
        label="Дата окончания",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )


class UUDDKDForm(forms.Form):
    """
    Форма для Участка устранения дефектов (DKD)
    """

    vin_number = forms.CharField(
        label="VIN номер",
        max_length=17,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите VIN"}),
    )

    repair_description = forms.CharField(
        label="Описание выполненного ремонта",
        required=True,
        max_length=1000,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Опишите как был устранён дефект..."}),
    )

    repair_photos = forms.FileField(
        label="Фото устранённых дефектов",
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),  # убираем multiple отсюда
    )

    def clean_repair_photos(self):
        """✅ Забираем список файлов вручную"""
        return self.files.getlist("repair_photos")


class UUDCheckForm(forms.Form):
    """
    Форма проверки ремонта на Участке устранения дефектов (DKD)
    """

    vin_number = forms.CharField(
        label="VIN-номер",
        max_length=17,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите VIN"})
    )

    CHECK_STATUS_CHOICES = [
        ("passed", "Проверку прошёл"),
        ("not_passed", "Проверку не прошёл"),
    ]

    check_status = forms.ChoiceField(
        label="Результат проверки",
        choices=CHECK_STATUS_CHOICES,
        widget=forms.RadioSelect,
        required=True
    )

    comment = forms.CharField(
        label="Комментарий (если не прошёл)",
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "placeholder": "Опишите, что не устранено",
            "rows": 3
        })
    )

    check_photos = forms.FileField(
        label="Фото недоработок",
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),  # ✅ без multiple
    )

    def clean_check_photos(self):
        """✅ Возвращаем список файлов вручную"""
        return self.files.getlist("check_photos")

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("check_status")
        comment = cleaned_data.get("comment")
        photos = self.files.getlist("check_photos")

        if status == "not_passed":
            if not comment:
                self.add_error("comment", "Пожалуйста, укажите комментарий при провале проверки.")
            if not photos:
                self.add_error("check_photos", "Пожалуйста, добавьте фото недоработок.")


class AssemblyTemplateForm(forms.Form):
    """
    Форма для шаблона сборки
    """

    vin_number = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите VIN"})
    )

    defect_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "placeholder": "Опишите дефект (если есть)", "rows": 4})
    )

    has_defect = forms.ChoiceField(
        choices=[("yes", "Есть дефект"), ("no", "Дефекта нет")],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        required=True
    )

    defect_photos = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
        label="Фото дефектов",
    )

    def clean_defect_photos(self):
        """
        ✅ Обрабатывает загруженные фото дефектов — возвращает список файлов (даже если одно фото).
        """
        files = self.files.getlist("defect_photos")
        return files if files else None


