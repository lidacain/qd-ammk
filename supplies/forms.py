from django import forms
from .models import ContainerUnloadingZone2Inspection, ContainerUnloadingZoneSBInspection, Detail, Defect, DefectGrade, DefectResponsible


class ContainerUnloadingZone2InspectionForm(forms.ModelForm):
    detail = forms.ModelChoiceField(
        queryset=Detail.objects.none(),
        required=True,
        widget=forms.Select(attrs={"class": "form-control", "id": "detail-select"})
    )

    defect = forms.ModelChoiceField(
        queryset=Defect.objects.none(),
        required=True,
        widget=forms.Select(attrs={"class": "form-control", "id": "defect-select"})
    )

    # ✅ Поддержка загрузки нескольких файлов
    defect_images = forms.FileField(
        widget=forms.FileInput(attrs={"class": "form-control"}),
        required=False
    )

    class Meta:
        model = ContainerUnloadingZone2Inspection
        fields = [
            "container_number", "pallet_number", "detail", "defect",
            "defect_description", "container_image", "pallet_image", "defect_images"
        ]
        widgets = {
            "container_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите номер контейнера"}),
            "pallet_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите номер пломбы"}),
            "defect_description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Опишите дефект"}),
            "container_image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "pallet_image": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        post = kwargs.pop("post", None)
        super().__init__(*args, **kwargs)

        if post:
            self.fields["detail"].queryset = Detail.objects.filter(posts=post)
            self.fields["defect"].queryset = Defect.objects.filter(posts=post)

        self.fields["detail"].empty_label = "Выберите деталь"
        self.fields["defect"].empty_label = "Выберите дефект"

    def clean_defect_images(self):
        """
        ✅ Обрабатывает загруженные изображения дефектов.
        - Возвращает список файлов.
        """
        images = self.files.getlist("defect_images")  # ✅ Теперь это список файлов

        if not images:
            return ""

        return images  # ✅ Теперь список файлов передаётся во `views.py`


class ContainerUnloadingZoneSBInspectionForm(forms.ModelForm):
    """Форма для инспекции зоны выгрузки контейнеров SB"""

    container_images = forms.FileField(
        widget=forms.FileInput(attrs={"class": "form-control"}),  # ❌ `multiple=True` убран
        required=False
    )

    container_number = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите номер контейнера"})
    )

    container_number_image = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
        required=False
    )

    container_description = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите описание контейнера"}),
        max_length=100,
        required=False
    )

    seal_image = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
        required=False
    )

    seal_description = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите описание пломбы"}),
        max_length=100,
        required=False
    )

    container_status = forms.ChoiceField(
        choices=ContainerUnloadingZoneSBInspection.CONTAINER_STATUS_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"}),
        required=True
    )

    class Meta:
        model = ContainerUnloadingZoneSBInspection
        fields = [
            "container_images", "container_number", "container_number_image",
            "container_description", "seal_image", "seal_description", "container_status"
        ]

    def clean_container_images(self):
        """
        ✅ Обрабатывает загруженные изображения контейнера.
        - Возвращает список файлов.
        """
        images = self.files.getlist("container_images")

        if not images:
            return ""

        return images


from django import forms
from .models import Detail, Defect, DefectGrade, DefectResponsible


class ComponentUnloadingZoneDKDForm(forms.Form):
    """Форма инспекции зоны выгрузки комплектующих (DKD)"""

    engine_number = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите номер двигателя"})
    )

    engine_photo = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"})
    )

    has_defect = forms.ChoiceField(
        choices=[("no", "online"), ("yes", "offline")],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        required=True
    )

    responsible = forms.ModelChoiceField(
        queryset=DefectResponsible.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "responsible-select"})
    )

    detail = forms.ModelChoiceField(
        queryset=Detail.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "detail-select"})
    )

    defect = forms.ModelChoiceField(
        queryset=Defect.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "defect-select"})
    )

    quantity = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Введите количество"})
    )

    grade = forms.ModelChoiceField(
        queryset=DefectGrade.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "grade-select"})
    )

    repair_type = forms.ChoiceField(
        choices=[("online", "online"), ("offline", "offline")],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        required=True
    )

    repair_type_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Описание ремонта (если был)"}),
    )

    defect_photos = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        post_id = kwargs.pop("post_id", None)
        super().__init__(*args, **kwargs)

        if post_id:
            self.fields["detail"].queryset = Detail.objects.filter(posts__id=post_id)
            self.fields["defect"].queryset = Defect.objects.filter(posts__id=post_id)

        self.fields["detail"].empty_label = "Выберите деталь"
        self.fields["defect"].empty_label = "Выберите дефект"

    def clean_repair_type(self):
        """✅ Возвращает только выбранный вариант ('Ремонт не был' или 'Ремонт был')"""
        return self.cleaned_data.get("repair_type")

    def clean_repair_type_description(self):
        """✅ Проверяем, есть ли описание ремонта, если выбрано 'Ремонт был'"""
        repair_type = self.cleaned_data.get("repair_type")
        description = self.cleaned_data.get("repair_type_description", "").strip()

        if repair_type == "Ремонт был" and not description:
            raise forms.ValidationError("Введите описание ремонта.")

        return description if repair_type == "Ремонт был" else ""

    def clean_defect_photos(self):
        """✅ Обрабатывает загруженные изображения дефектов и возвращает список файлов"""
        return self.files.getlist("defect_photos") or None


class BodyUnloadingZoneDKDForm(forms.Form):
    """Форма инспекции зоны первичного осмотра кузовов (DKD)"""

    vin_number = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите VIN номер"})
    )

    container_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите номер контейнера"})
    )

    body_photos = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={"class": "form-control"}),
    )

    has_defect = forms.ChoiceField(
        choices=[("no", "Дефекта нет"), ("yes", "Есть дефект")],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        required=True
    )

    responsible = forms.ModelChoiceField(
        queryset=DefectResponsible.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "responsible-select"})
    )

    detail = forms.ModelChoiceField(
        queryset=Detail.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "detail-select"})
    )

    defect = forms.ModelChoiceField(
        queryset=Defect.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "defect-select"})
    )

    quantity = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Введите количество"})
    )

    grade = forms.ModelChoiceField(
        queryset=DefectGrade.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "grade-select"})
    )

    defect_photos = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        post_id = kwargs.pop("post_id", None)
        super().__init__(*args, **kwargs)

        if post_id:
            self.fields["detail"].queryset = Detail.objects.filter(posts__id=post_id)
            self.fields["defect"].queryset = Defect.objects.filter(posts__id=post_id)

        self.fields["detail"].empty_label = "Выберите деталь"
        self.fields["defect"].empty_label = "Выберите дефект"

    def clean_repair_type(self):
        """Обрабатывает поле repair_type и возвращает корректное значение"""
        repair_type = self.cleaned_data.get("repair_type")
        if not repair_type:
            raise forms.ValidationError("Поле 'Тип ремонта' обязательно.")
        return repair_type

    def clean_body_photos(self):
        """✅ Обрабатывает загруженные изображения кузова и возвращает список файлов"""
        return self.files.getlist("body_photos") or None

    def clean_defect_photos(self):
        """✅ Обрабатывает загруженные изображения дефектов и возвращает список файлов"""
        return self.files.getlist("defect_photos") or None


class MainUnloadingZoneDKDForm(forms.Form):
    """Форма инспекции зоны основной приемки DKD"""

    vin_number = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите VIN номер"})
    )

    body_photos = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={"class": "form-control"}),
    )

    has_defect = forms.ChoiceField(
        choices=[("no", "Дефекта нет"), ("yes", "Есть дефект")],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        required=True
    )

    responsible = forms.ModelChoiceField(
        queryset=DefectResponsible.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "responsible-select"})
    )

    detail = forms.ModelChoiceField(
        queryset=Detail.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "detail-select"})
    )

    defect = forms.ModelChoiceField(
        queryset=Defect.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "defect-select"})
    )

    quantity = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Введите количество"})
    )

    grade = forms.ModelChoiceField(
        queryset=DefectGrade.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "grade-select"})
    )

    defect_photos = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        post_id = kwargs.pop("post_id", None)
        super().__init__(*args, **kwargs)

        if post_id:
            self.fields["detail"].queryset = Detail.objects.filter(posts__id=post_id)
            self.fields["defect"].queryset = Defect.objects.filter(posts__id=post_id)

        self.fields["detail"].empty_label = "Выберите деталь"
        self.fields["defect"].empty_label = "Выберите дефект"

    def clean_body_photos(self):
        """✅ Обрабатывает загруженные изображения кузова и возвращает список файлов"""
        return self.files.getlist("body_photos") or None

    def clean_defect_photos(self):
        """✅ Обрабатывает загруженные изображения дефектов и возвращает список файлов"""
        return self.files.getlist("defect_photos") or None


class ContainerInspectionForm(forms.Form):
    """Форма осмотра контейнера (DKD)"""

    container_number = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите номер контейнера"})
    )

    container_photos = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={"class": "form-control"}),  # ❌ без multiple
    )

    has_defect = forms.ChoiceField(
        choices=[("no", "Дефекта нет"), ("yes", "Есть дефект")],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        required=True
    )

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Опишите состояние контейнера или дефект (если есть)"
        })
    )

    def clean_container_photos(self):
        """✅ Обрабатываем фото вручную как список, даже если в форме одно поле"""
        return self.files.getlist("container_photos") or None
