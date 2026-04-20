from django import forms
from django.utils.translation import gettext_lazy as _

from apps.app_entity.models import Entity, Stakeholder, StakeholderRole


class PurchaseWizardStep1Form(forms.Form):
    """Form for purchase wizard step 1: basic info (date, vendor, description)."""

    date = forms.DateField(
        label=_("Date"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    vendor = forms.ModelChoiceField(
        label=_("Vendor"),
        queryset=Entity.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    description = forms.CharField(
        label=_("Description"),
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project is not None:
            vendor_ids = Stakeholder.objects.filter(
                parent=project,
                role=StakeholderRole.VENDOR,
                active=True,
            ).values_list("target_id", flat=True)
            self.fields["vendor"].queryset = Entity.objects.filter(pk__in=vendor_ids)
