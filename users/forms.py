from django import forms
from .models import CustomUser, Selection, Employee
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.forms import PasswordChangeForm
from datetime import timedelta, date
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile
from assembly.models import AssemblyZone, AssemblyUnit, AssemblyDefect


class ControllerCreationForm(forms.ModelForm):
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={"placeholder": "Введите пароль"})
    )
    password2 = forms.CharField(
        label="Повторите пароль",
        widget=forms.PasswordInput(attrs={"placeholder": "Повторите пароль"})
    )
    username = forms.CharField(
        label="Имя пользователя",
        widget=forms.TextInput(attrs={"placeholder": "Введите логин"})
    )
    first_name = forms.CharField(
        label="Имя",
        widget=forms.TextInput(attrs={"placeholder": "Введите имя"})
    )
    last_name = forms.CharField(
        label="Фамилия",
        widget=forms.TextInput(attrs={"placeholder": "Введите фамилию"})
    )
    patronymic = forms.CharField(
        label="Отчество",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Введите отчество (необязательно)"})
    )
    email = forms.EmailField(
        label="Email",
        required=False,
        widget=forms.EmailInput(attrs={"placeholder": "Введите почту (необязательно)"})
    )

    class Meta:
        model = CustomUser
        fields = ['username', 'password', 'password2', 'first_name', 'last_name', 'patronymic', 'email']


    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("password2")

        if p1 and p2 and p1 != p2:
            raise ValidationError("Пароли не совпадают.")

        try:
            validate_password(p1)
        except ValidationError as e:
            raise ValidationError(e.messages)

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.role = 'controller'
        if commit:
            user.save()
        return user


class ControllerPasswordChangeForm(forms.Form):
    new_password = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(attrs={"placeholder": "Введите новый пароль", "class": "form-control"})
    )
    password2 = forms.CharField(
        label="Повторите пароль",
        widget=forms.PasswordInput(attrs={"placeholder": "Повторите новый пароль", "class": "form-control"})
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("new_password")
        p2 = cleaned_data.get("password2")

        if p1 and p2 and p1 != p2:
            raise ValidationError("Пароли не совпадают.")

        try:
            validate_password(p1)
        except ValidationError as e:
            raise ValidationError(e.messages)

        return cleaned_data


class ControllerEditForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'patronymic', 'email', 'position', 'avatar']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'patronymic': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'position': forms.TextInput(attrs={'class': 'form-control'}),  # 👈 добавлено
            'avatar': forms.FileInput(attrs={'class': 'form-control'}),
        }


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'patronymic', 'email', 'position', 'avatar']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control form-control-lg'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control form-control-lg'}),
            'patronymic': forms.TextInput(attrs={'class': 'form-control form-control-lg'}),
            'email': forms.EmailInput(attrs={'class': 'form-control form-control-lg'}),
            'position': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'Укажите вашу должность'
            }),
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar:
            try:
                image = Image.open(avatar)
                image = image.convert('RGB')  # Убедимся, что RGB (на случай PNG и др.)

                width, height = image.size
                min_side = min(width, height)

                # Координаты для центрированной обрезки
                left = (width - min_side) // 2
                top = (height - min_side) // 2
                right = left + min_side
                bottom = top + min_side

                image = image.crop((left, top, right, bottom))
                image = image.resize((400, 400))  # Можно изменить на нужный размер

                buffer = BytesIO()
                image.save(buffer, format='JPEG', quality=90)
                return ContentFile(buffer.getvalue(), name=avatar.name)

            except Exception as e:
                raise forms.ValidationError("Ошибка обработки изображения.")
        return avatar


class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].widget.attrs.update({
            'class': 'form-control form-control-lg',
            'id': 'old_password'
        })
        self.fields['new_password1'].widget.attrs.update({
            'class': 'form-control form-control-lg',
            'id': 'new_password1'
        })
        self.fields['new_password2'].widget.attrs.update({
            'class': 'form-control form-control-lg',
            'id': 'new_password2'
        })


class EmployeeSearchForm(forms.Form):
    search_query = forms.CharField(
        label='Поиск по ФИО',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите ФИО сотрудника'
        })
    )
    position = forms.CharField(
        label='Должность',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите должность'
        })
    )
    department = forms.CharField(
        label='Отдел / группа',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите отдел / группу'
        })
    )


class EmployeeSelectionForm(forms.Form):
    TIME_CHOICES = [
        (f"{h:02d}:{m:02d}", f"{h:02d}:{m:02d}")
        for h in range(7, 21)
        for m in (0, 30)
    ]

    employees = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.none(),  # временно пусто, будет переопределено
        label="Сотрудники",
        widget=forms.SelectMultiple(attrs={
            'class': 'form-select select2',
            'multiple': 'multiple',
            'data-placeholder': 'Выберите одного или несколько сотрудников'
        })
    )

    selected_dates = forms.CharField(
        label="Выберите даты",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'date-picker',
            'placeholder': 'Выберите дату(ы)'
        })
    )

    start_time = forms.ChoiceField(
        label="Начало работы",
        choices=TIME_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    end_time = forms.ChoiceField(
        label="Окончание работы",
        choices=TIME_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    is_xtk = forms.BooleanField(
        label="ХТК",
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    justification = forms.CharField(
        label="Обоснование",
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Напишите причину/назначение выбора этих сотрудников',
            'rows': 2
        })
    )

    def __init__(self, *args, **kwargs):
        selected_ids = []
        if 'data' in kwargs:
            selected_ids = kwargs['data'].getlist('employees')
        elif 'initial' in kwargs:
            selected_ids = kwargs['initial'].get('employees', [])

        super().__init__(*args, **kwargs)
        if selected_ids:
            self.fields['employees'].queryset = Employee.objects.filter(id__in=selected_ids)
        else:
            self.fields['employees'].queryset = Employee.objects.all()

    def clean_selected_dates(self):
        dates_str = self.cleaned_data['selected_dates']
        date_list = [s.strip() for s in dates_str.split(',') if s.strip()]
        if not date_list:
            raise forms.ValidationError("Выберите хотя бы одну дату")
        return date_list

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_time")
        end = cleaned_data.get("end_time")
        if start and end and start[-2:] != end[-2:]:
            raise forms.ValidationError("Начало и окончание работы должны быть либо оба с :00, либо оба с :30")
        return cleaned_data


class AssemblyZoneForm(forms.ModelForm):
    class Meta:
        model = AssemblyZone
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }


class AssemblyUnitForm(forms.ModelForm):
    class Meta:
        model = AssemblyUnit
        fields = ['name', 'zone']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'zone': forms.Select(attrs={'class': 'form-select form-select-sm'}),
        }


class AssemblyDefectForm(forms.ModelForm):
    class Meta:
        model = AssemblyDefect
        fields = ['name', 'nameENG']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'nameENG': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }