"""Forms for the operation app.

Provides the multi-step purchase and sale wizard forms (step forms plus the
per-item item forms), the :class:`PaymentForm` for recording payments /
repayments, and :class:`EvaluationForm` for capital-valuation operations.
"""

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.app_base.form_logging import LoggingFormMixin
from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import Product


class PurchaseWizardStep1Form(LoggingFormMixin, forms.Form):
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
            # Internal entities cannot be vendors — purchases are external-only.
            # The World entity is always offered as an ad-hoc vendor (no
            # Stakeholder record required) so one-off purchases can be recorded.
            from django.db.models import Q

            self.fields["vendor"].queryset = Entity.objects.filter(
                Q(pk__in=vendor_ids) | Q(entity_type=EntityType.WORLD)
            ).exclude(is_internal=True)


class PurchaseWizardStep2Form(LoggingFormMixin, forms.Form):
    """Form for purchase wizard step 2: declared invoice total."""

    total_amount = forms.DecimalField(
        label=_("Total Invoice Amount"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=20,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control amount-input",
                "step": "0.01",
                "placeholder": "0.00",
                "inputmode": "decimal",
            }
        ),
    )


class PurchaseWizardStep3Form(LoggingFormMixin, forms.Form):
    """Form for purchase wizard step 3: optional initial payment."""

    amount_paid = forms.DecimalField(
        label=_("Payment Amount"),
        min_value=Decimal("0"),
        decimal_places=2,
        max_digits=20,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control amount-input",
                "step": "0.01",
                "placeholder": "0.00",
                "inputmode": "decimal",
            }
        ),
    )

    def clean_amount_paid(self):
        value = self.cleaned_data.get("amount_paid")
        return value if value is not None else Decimal("0")


class PurchaseItemForm(LoggingFormMixin, forms.Form):
    """Form for adding or editing a single invoice item in the purchase invoice view."""

    product_template_id = forms.IntegerField(widget=forms.HiddenInput)

    description = forms.CharField(
        label=_("Description"),
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Optional")}
        ),
    )

    quantity = forms.DecimalField(
        label=_("Quantity"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=10,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control amount-input",
                "step": "0.01",
                "inputmode": "decimal",
            }
        ),
    )

    unit_price = forms.DecimalField(
        label=_("Unit Price"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=15,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control amount-input",
                "step": "0.01",
                "inputmode": "decimal",
            }
        ),
    )

    unique_id = forms.CharField(
        label=_("Tag / ID"),
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Tag / ID")}
        ),
    )

    received_qty = forms.DecimalField(
        label=_("Received Qty"),
        min_value=Decimal("0"),
        decimal_places=2,
        max_digits=10,
        required=False,
        initial=Decimal("0"),
        help_text=_("Quantity physically received (0 = none yet)"),
        widget=forms.NumberInput(
            attrs={
                "class": "form-control amount-input",
                "step": "0.01",
                "inputmode": "decimal",
            }
        ),
    )

    def __init__(self, *args, template=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._template = template
        if template:
            step = str(template.minimum_quantity)
            self.fields["quantity"].widget.attrs["step"] = step
            self.fields["received_qty"].widget.attrs["step"] = step

    def clean(self):
        cleaned: dict = super().clean() or {}

        # The Tag / ID is optional and left entirely to the user: a blank value
        # is forwarded as-is (the backend auto-numbers the heads when the
        # products are created). The add-item view shows the next available tag
        # as a hint, but never fills the field in.

        received: Decimal = cleaned.get("received_qty") or Decimal("0")
        qty: Decimal = cleaned.get("quantity") or Decimal("0")
        if received > qty:
            self.add_error(
                "received_qty", _("Received quantity cannot exceed ordered quantity.")
            )

        cleaned["received_qty"] = received
        return cleaned


class SaleWizardStep1Form(LoggingFormMixin, forms.Form):
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


class SaleWizardStep2Form(LoggingFormMixin, forms.Form):
    """Form for sale wizard step 2: declared invoice total."""

    total_amount = forms.DecimalField(
        label=_("Total Invoice Amount"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=20,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control amount-input",
                "step": "0.01",
                "placeholder": "0.00",
                "inputmode": "decimal",
            }
        ),
    )


class SaleWizardStep3Form(LoggingFormMixin, forms.Form):
    """Form for sale wizard step 3: optional initial payment."""

    amount_paid = forms.DecimalField(
        label=_("Payment Amount"),
        min_value=Decimal("0"),
        decimal_places=2,
        max_digits=20,
        required=False,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control amount-input",
                "step": "0.01",
                "placeholder": "0.00",
                "inputmode": "decimal",
            }
        ),
    )

    def clean_amount_paid(self):
        value = self.cleaned_data.get("amount_paid")
        return value if value is not None else Decimal("0")


class SaleItemForm(LoggingFormMixin, forms.Form):
    """Form for adding/editing a sale invoice item — selects an EXISTING product
    from the seller's stock. The sale affects that product (a SALE_MOVEMENT line
    reduces its presence / marks it SOLD); no new product is minted."""

    product_id = forms.IntegerField(widget=forms.HiddenInput)

    description = forms.CharField(
        label=_("Description"),
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Optional")}
        ),
    )

    quantity = forms.DecimalField(
        label=_("Quantity"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=10,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control amount-input",
                "step": "0.01",
                "inputmode": "decimal",
            }
        ),
    )

    unit_price = forms.DecimalField(
        label=_("Unit Price"),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=15,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control amount-input",
                "step": "0.01",
                "inputmode": "decimal",
            }
        ),
    )

    def __init__(self, *args, product=None, entity=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._product = product
        self._entity = entity
        if product is not None:
            step = str(product.product_template.minimum_quantity)
            self.fields["quantity"].widget.attrs["step"] = step

    def clean(self):
        from datetime import date

        from apps.app_inventory.models import Product
        from apps.app_inventory.stock import movement_state

        cleaned: dict = super().clean() or {}

        # Resolve the product being sold (passed in by the view, but re-validated
        # here so a crafted request cannot bypass ownership/availability).
        product = self._product
        if product is None:
            product_id = cleaned.get("product_id")
            if product_id:
                product = Product.objects.filter(pk=product_id).first()
        if product is None:
            self.add_error(
                "product_id", _("Please choose a product from your stock.")
            )
            return cleaned

        # Ownership: the product must belong to the selling project.
        if self._entity is not None and product.entity_id != self._entity.id:
            self.add_error(
                "product_id",
                _("Product does not belong to this project and cannot be sold."),
            )
            return cleaned

        # Status: cannot sell a product that is already SOLD/DEAD/CONSUMED.
        try:
            product.validate_active()
        except ValidationError as e:
            self.add_error(
                "product_id", e.messages[0] if e.messages else str(e)
            )
            return cleaned

        # Availability: cannot sell more than the physically-present on-hand.
        qty: Decimal = cleaned.get("quantity") or Decimal("0")
        available = movement_state(product, as_of=date.today())["quantity"]
        if qty > available:
            self.add_error(
                "quantity",
                _("Only %(avail)s available in stock.") % {"avail": available},
            )

        cleaned["product"] = product
        cleaned["available"] = available
        return cleaned


class PaymentForm(LoggingFormMixin, forms.Form):
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
            attrs={
                "class": "form-control amount-input",
                "step": "0.01",
                "placeholder": "0.00",
                "inputmode": "decimal",
            }
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


class EvaluationForm(forms.Form):
    """Form for evaluating a product at a new unit price (capital gain/loss)."""

    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        label=_("Product"),
        empty_label=_("— Select a product —"),
    )
    new_unit_price = forms.DecimalField(
        label=_("New unit price"),
        min_value=Decimal("0.01"),
        max_digits=15,
        decimal_places=2,
    )
    date = forms.DateField(
        label=_("Date"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    description = forms.CharField(
        label=_("Notes"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            # Ownership-restricted: only products physically owned by the project
            # can be evaluated (avoids recording a gain/loss on another entity's
            # asset just because its template is assigned here).
            self.fields["product"].queryset = (
                Product.objects.filter(entity=project)
                .select_related("product_template")
                .order_by("product_template__name", "pk")
            )
        if not self.data and "date" not in kwargs.get("initial", {}):
            self.fields["date"].initial = timezone.now().date()
