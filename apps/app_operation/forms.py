from decimal import Decimal

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


class PurchaseWizardStep2Form(forms.Form):
    """Form for purchase wizard step 2: declared invoice total."""

    total_amount = forms.DecimalField(
        label=_("Total Invoice Amount"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=20,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}
        ),
    )


class PurchaseWizardStep3Form(forms.Form):
    """Form for purchase wizard step 3: optional initial payment."""

    amount_paid = forms.DecimalField(
        label=_("Payment Amount"),
        min_value=Decimal("0"),
        decimal_places=2,
        max_digits=20,
        required=False,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}
        ),
    )

    def clean_amount_paid(self):
        value = self.cleaned_data.get("amount_paid")
        return value if value is not None else Decimal("0")


class PurchaseItemForm(forms.Form):
    """Form for adding or editing a single invoice item in the purchase invoice view."""

    product_template_id = forms.IntegerField(widget=forms.HiddenInput)

    description = forms.CharField(
        label=_("Description"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": _("Optional")}),
    )

    quantity = forms.DecimalField(
        label=_("Quantity"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=10,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    unit_price = forms.DecimalField(
        label=_("Unit Price"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=15,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    unique_id = forms.CharField(
        label=_("Tag / ID"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": _("Tag / ID")}),
    )

    received_qty = forms.DecimalField(
        label=_("Received Qty"),
        min_value=Decimal("0"),
        decimal_places=2,
        max_digits=10,
        required=False,
        initial=Decimal("0"),
        help_text=_("Quantity physically received (0 = none yet)"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    def __init__(self, *args, template=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._template = template

    def clean(self):
        cleaned: dict = super().clean() or {}
        template = self._template

        if template and template.requires_individual_tag:
            uid = (cleaned.get("unique_id") or "").strip()
            if not uid:
                self.add_error("unique_id", _("Tag / ID is required for this product."))

        received: Decimal = cleaned.get("received_qty") or Decimal("0")
        qty: Decimal = cleaned.get("quantity") or Decimal("0")
        if received > qty:
            self.add_error("received_qty", _("Received quantity cannot exceed ordered quantity."))

        cleaned["received_qty"] = received
        return cleaned


class SaleWizardStep1Form(forms.Form):
    """Form for sale wizard step 1: basic info (date, client, description)."""

    date = forms.DateField(
        label=_("Date"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    client = forms.ModelChoiceField(
        label=_("Client"),
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
            client_ids = Stakeholder.objects.filter(
                parent=project,
                role=StakeholderRole.CLIENT,
                active=True,
            ).values_list("target_id", flat=True)
            self.fields["client"].queryset = Entity.objects.filter(pk__in=client_ids)


class SaleWizardStep2Form(forms.Form):
    """Form for sale wizard step 2: declared invoice total."""

    total_amount = forms.DecimalField(
        label=_("Total Invoice Amount"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=20,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}
        ),
    )


class SaleWizardStep3Form(forms.Form):
    """Form for sale wizard step 3: optional initial payment."""

    amount_paid = forms.DecimalField(
        label=_("Payment Amount"),
        min_value=Decimal("0"),
        decimal_places=2,
        max_digits=20,
        required=False,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}
        ),
    )

    def clean_amount_paid(self):
        value = self.cleaned_data.get("amount_paid")
        return value if value is not None else Decimal("0")


class SaleItemForm(forms.Form):
    """Form for adding or editing a single invoice item in the sale invoice view."""

    product_template_id = forms.IntegerField(widget=forms.HiddenInput)

    description = forms.CharField(
        label=_("Description"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": _("Optional")}),
    )

    quantity = forms.DecimalField(
        label=_("Quantity"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=10,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    unit_price = forms.DecimalField(
        label=_("Unit Price"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=15,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    unique_id = forms.CharField(
        label=_("Tag / ID"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": _("Tag / ID")}),
    )

    delivered_qty = forms.DecimalField(
        label=_("Delivered Qty"),
        min_value=Decimal("0"),
        decimal_places=2,
        max_digits=10,
        required=False,
        initial=Decimal("0"),
        help_text=_("Quantity physically delivered (0 = none yet)"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    def __init__(self, *args, template=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._template = template

    def clean(self):
        cleaned: dict = super().clean() or {}
        template = self._template

        if template and template.requires_individual_tag:
            uid = (cleaned.get("unique_id") or "").strip()
            if not uid:
                self.add_error("unique_id", _("Tag / ID is required for this product."))

        delivered: Decimal = cleaned.get("delivered_qty") or Decimal("0")
        qty: Decimal = cleaned.get("quantity") or Decimal("0")
        if delivered > qty:
            self.add_error("delivered_qty", _("Delivered quantity cannot exceed ordered quantity."))

        cleaned["delivered_qty"] = delivered
        return cleaned


class PaymentForm(forms.Form):
    """Form for recording a payment transaction on an operation."""

    date = forms.DateField(
        label=_("Date"),
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    amount = forms.DecimalField(
        label=_("Payment Amount"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=20,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}
        ),
    )

    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount and amount < Decimal("0.01"):
            raise forms.ValidationError(_("Amount must be at least 0.01."))
        return amount
