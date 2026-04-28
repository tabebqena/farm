from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.app_base.form_logging import LoggingFormMixin
from apps.app_operation.models.operation import Operation
from .models import (
    InvoiceItem,
    InventoryMovement,
    InventoryMovementLine,
    Product,
    ProductTemplate,
)


# ---------------------------------------------------------------------------
# Create-mode: used by PURCHASE and BIRTH
# Each form row specifies a ProductTemplate + quantity/price.
# The view creates a Product instance from each saved InvoiceItem.
# ---------------------------------------------------------------------------


class RequiresTagSelect(forms.Select):
    """Select widget that stamps each ProductTemplate option with data-requires-tag."""

    def __init__(self, *args, **kwargs):
        self.requires_tag_pks = set()
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subgroup=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subgroup=subgroup, attrs=attrs)
        if value:
            pk = str(value.value if hasattr(value, "value") else value)
            option["attrs"]["data-requires-tag"] = "true" if pk in self.requires_tag_pks else "false"
        return option


class InvoiceItemCreateForm(LoggingFormMixin, forms.ModelForm):
    """
    One row = one Product to be created (animal born / purchased).
    `unique_id` is an extra non-model field: required for INDIVIDUAL tracking,
    optional otherwise — the view enforces this after checking the template's
    tracking_mode.

    Pass `project` (an Entity instance) to filter the `product` dropdown to
    only ProductTemplates linked to that project.
    """

    product = forms.ModelChoiceField(
        queryset=ProductTemplate.objects.all(),
        label="Product",
        empty_label="— select —",
        required=False,
        widget=RequiresTagSelect(attrs={"class": "form-select form-select-sm product-select"}),
    )
    unique_id = forms.CharField(
        required=False,
        label="Tag / ID",
        help_text="Required for individually tracked animals.",
        widget=forms.TextInput(
            attrs={"class": "form-control form-control-sm", "placeholder": "Tag / ID"}
        ),
    )

    class Meta:
        model = InvoiceItem
        fields = ("product", "description", "quantity", "unit_price")
        # `product` here is the FK to ProductTemplate (what type is being acquired)
        widgets = {
            "description": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "placeholder": "Description (optional)",
                }
            ),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project is not None:
            qs = ProductTemplate.objects.filter(entities=project)
            self.fields["product"].queryset = qs
            self.fields["product"].widget.requires_tag_pks = set(
                str(pk) for pk in qs.filter(requires_individual_tag=True).values_list("pk", flat=True)
            )
        self.fields["unit_price"].required = False

    def clean(self):
        cleaned = super().clean()
        template = cleaned.get("product")
        uid = cleaned.get("unique_id", "").strip()

        # If product is selected, require unit_price
        if template and not cleaned.get("unit_price"):
            self.add_error("unit_price", "Unit price is required when a product is selected.")

        # If product is selected and requires individual tag, validate unique_id
        if template and template.requires_individual_tag and not uid:
            self.add_error(
                "unique_id", "Tag / ID is required for individually tracked animals."
            )
        return cleaned


class BaseInvoiceItemCreateFormSet(BaseInlineFormSet):
    """Passes `project` down to each InvoiceItemCreateForm."""

    def __init__(self, *args, project=None, **kwargs):
        self.project = project
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["project"] = self.project
        return kwargs


InvoiceItemCreateFormSet = inlineformset_factory(
    Operation,
    InvoiceItem,
    form=InvoiceItemCreateForm,
    formset=BaseInvoiceItemCreateFormSet,
    extra=1,
    can_delete=True,
)


# ---------------------------------------------------------------------------
# Select-mode: used by SALE, DEATH, CAPITAL_GAIN, CAPITAL_LOSS
# Each form row picks an existing Product (animal/batch) and records the
# price/quantity for this operation.
# The view links the saved InvoiceItem back to the Product via M2M.
# ---------------------------------------------------------------------------


class InvoiceItemSelectForm(LoggingFormMixin, forms.ModelForm):
    """
    One row = one existing Product being referenced (sold / died / gained / lost).
    `selected_product` is a non-model field — the view resolves the M2M link.
    The ProductTemplate FK on InvoiceItem is filled from the selection.
    """

    selected_product = forms.ModelChoiceField(
        queryset=Product.objects.select_related("product_template").all(),
        label="Animal / Batch",
        empty_label="— select —",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    class Meta:
        model = InvoiceItem
        fields = ("quantity", "unit_price", "description")
        widgets = {
            "description": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "placeholder": "Description (optional)",
                }
            ),
        }

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("selected_product")
        if product:
            product.validate_active()
            # Derive the required ProductTemplate FK from the selected Product
            self.instance.product = product.product_template
        return cleaned


InvoiceItemSelectFormSet = inlineformset_factory(
    Operation,
    InvoiceItem,
    form=InvoiceItemSelectForm,
    extra=1,
    can_delete=True,
)


# ---------------------------------------------------------------------------
# Inventory Movement Line: used to record physical movement of items
# Each form row specifies an InvoiceItem and the quantity being moved.
# ---------------------------------------------------------------------------


class InventoryMovementLineForm(LoggingFormMixin, forms.ModelForm):
    """
    One row = one InvoiceItem being physically moved (received/dispatched).
    Pass `operation` to filter the `invoice_item` dropdown to only items
    belonging to that operation.
    """

    invoice_item = forms.ModelChoiceField(
        queryset=InvoiceItem.objects.all(),
        label="Invoice Item",
        empty_label="— select —",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    class Meta:
        model = InventoryMovementLine
        fields = ("invoice_item", "quantity")
        widgets = {
            "quantity": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
        }

    def __init__(self, *args, operation=None, **kwargs):
        super().__init__(*args, **kwargs)
        if operation is not None:
            self.fields["invoice_item"].queryset = InvoiceItem.objects.filter(
                operation=operation
            ).select_related("product")


class BaseInventoryMovementLineFormSet(BaseInlineFormSet):
    """Passes `operation` down to each InventoryMovementLineForm."""

    def __init__(self, *args, operation=None, **kwargs):
        self.operation = operation
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["operation"] = self.operation
        return kwargs


InventoryMovementLineFormSet = inlineformset_factory(
    InventoryMovement,
    InventoryMovementLine,
    form=InventoryMovementLineForm,
    formset=BaseInventoryMovementLineFormSet,
    extra=1,
    can_delete=False,
)
