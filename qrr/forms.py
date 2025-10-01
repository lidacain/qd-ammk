from django import forms
from .models import (
    QRRInvestigation,
    InvestigationFactor,
    FactorCheck,
    InvestigationRequest,
    InvestigationResponsibility
)


class QRRInvestigationForm(forms.ModelForm):
    class Meta:
        model = QRRInvestigation
        exclude = [
            'created_by', 'submitted_by', 'submitted_at',
            'confirmed_at', 'created_at', 'form_number',
            'form_date', 'form_time'
        ]
        widgets = {
            'performed_by_user': forms.Select(attrs={'class': 'form-select'}),
            'performed_by_name': forms.TextInput(attrs={'class': 'form-control'}),
            'confirmed_by_user': forms.Select(attrs={'class': 'form-select'}),
            'confirmed_by_name': forms.TextInput(attrs={'class': 'form-control'}),
            'shift': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            # остальные поля можно добавить аналогично при желании кастомизации
        }


class InvestigationFactorForm(forms.ModelForm):
    class Meta:
        model = InvestigationFactor
        exclude = ['investigation']
        widgets = {
            'category': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class FactorCheckForm(forms.ModelForm):
    class Meta:
        model = FactorCheck
        exclude = ['investigation']
        widgets = {
            'factor_text': forms.TextInput(attrs={'class': 'form-control'}),
            'check_method': forms.TextInput(attrs={'class': 'form-control'}),
            'responsible': forms.TextInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'result': forms.Select(attrs={'class': 'form-select'}),
            'factor_type': forms.TextInput(attrs={'class': 'form-control'}),
        }


class InvestigationRequestForm(forms.ModelForm):
    class Meta:
        model = InvestigationRequest
        exclude = ['investigation']
        widgets = {
            'factor': forms.TextInput(attrs={'class': 'form-control'}),
            'action': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'responsible': forms.TextInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'result': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class InvestigationResponsibilityForm(forms.ModelForm):
    class Meta:
        model = InvestigationResponsibility
        exclude = ['investigation']
        widgets = {
            'factor': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'crcr_number': forms.TextInput(attrs={'class': 'form-control'}),
            'ktm_number': forms.TextInput(attrs={'class': 'form-control'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
