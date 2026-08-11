import uuid
from datetime import date
from decimal import Decimal

from django import forms
from django.forms import BaseModelFormSet, modelformset_factory
from django.utils.translation import gettext_lazy as _

from apps.app_base.form_logging import LoggingFormMixin
from apps.app_operation.models.operation import Operation

from .models import (
    InventoryMovementLine,
    InvoiceItem,
    Product,
    ProductTemplate,
)


class ProductTemplateForm(LoggingFormMixin, forms.ModelForm):
    """Create/edit a Product Template including the animal-specific attributes."""

    class Meta:
        model = ProductTemplate
        fields = (
            "name",
            "nature",
            "sub_category",
            "default_unit",
            "has_tag",
            "tag_prefix",
            "animal_type",
            "gender",
            "produces",
            "gives_birth_to",
            "can_die",
            "can_be_consumed",
        )
        widgets = {
            "animal_type": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("e.g. Cow, Buffalo, Sheep, Goat"),
                }
            ),
            "sub_category": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("e.g. Cattle, Poultry")}
            ),
            "default_unit": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("e.g. Head, Kg, Liter")}
            ),
            "tag_prefix": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("e.g. CALF, COW, LAMB")}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 'produces' may only reference output (FEED/PRODUCT) templates.
        self.fields["produces"].queryset = ProductTemplate.objects.filter(
            nature__in=(ProductTemplate.Nature.FEED, ProductTemplate.Nature.PRODUCT)
        )
        # 'gives_birth_to' must reference an ANIMAL template.
        self.fields["gives_birth_to"].queryset = ProductTemplate.objects.filter(
            nature=ProductTemplate.Nature.ANIMAL
        )
        self.fields["produces"].required = False
        self.fields["gives_birth_to"].required = False

    def clean(self):
        cleaned = super().clean()
        nature = cleaned.get("nature")
        if nature == ProductTemplate.Nature.ANIMAL:
            # No animal can be consumed — force the flag off.
            cleaned["can_be_consumed"] = False
        return cleaned


# ---------------------------------------------------------------------------
# Create-mode: used by PURCHASE and BIRTH
# Each form row specifies a ProductTemplate + quantity/price.
# The view creates a Product instance from each saved InvoiceItem.
# ---------------------------------------------------------------------------


class HasTagSelect(forms.Select):
    """Select widget that stamps each ProductTemplate option with data-has-tag."""

    def __init__(self, *args, **kwargs):
        self.has_tag_pks = set()
        super().__init__(*args, **kwargs)

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        if value:
            pk = str(value.value if hasattr(value, "value") else value)
            option["attrs"]["data-has-tag"] = (
                "true" if pk in self.has_tag_pks else "false"
            )
        return option


class InvoiceItemCreateForm(LoggingFormMixin, forms.ModelForm):
    """
    One row = one Product (or a bulk batch for COMMODITY) to be created.
    `unique_id` is an extra non-model field: for INDIVIDUAL (ANIMAL) tracking
    it is auto-suggested from the template's tag prefix and editable; optional
    for COMMODITY templates.

    A bulk quantity is allowed for INDIVIDUAL templates — the backend creates
    one tagged Product per head.

    Pass `project` (an Entity instance) to filter the `product` dropdown to
    only ProductTemplates linked to that project.
    """

    product_template = forms.ModelChoiceField(
        queryset=ProductTemplate.objects.all(),
        label="Product",
        empty_label="— select —",
        required=False,
        widget=HasTagSelect(
            attrs={"class": "form-select form-select-sm product-select"}
        ),
    )
    unique_id = forms.CharField(
        required=False,
        label="Tag / ID",
        help_text="Auto-suggested for individually tracked animals; editable.",
        widget=forms.TextInput(
            attrs={"class": "form-control form-control-sm", "placeholder": "Tag / ID"}
        ),
    )

    # Birth-only fields: used when ``is_birth=True`` (see __init__).
    mother = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        required=False,
        label="Mother",
        empty_label="— select mother —",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    gender = forms.ChoiceField(
        choices=(
            ("", "— select —"),
            ("MALE", "Male"),
            ("FEMALE", "Female"),
        ),
        required=False,
        label="Gender",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    birth_date = forms.DateField(
        required=False,
        label="Birth Date",
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control form-control-sm"}
        ),
    )

    class Meta:
        model = InvoiceItem
        fields = ("product_template", "description", "quantity", "unit_price")
        # `product_template` here is the FK to ProductTemplate (what type is being acquired)
        widgets = {
            "description": forms.TextInput(
                attrs={
                    "class": "form-control form-control-sm",
                    "placeholder": "Description (optional)",
                }
            ),
            "quantity": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm amount-input qty-input",
                    "step": "0.01",
                    "inputmode": "decimal",
                }
            ),
            "unit_price": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm amount-input price-input",
                    "step": "0.01",
                    "inputmode": "decimal",
                }
            ),
        }

    def __init__(self, *args, project=None, is_birth=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.is_birth = is_birth
        if project is not None:
            qs = ProductTemplate.objects.filter(entities=project)
            self.fields["product_template"].queryset = qs
            self.fields["product_template"].widget.has_tag_pks = set(
                str(pk) for pk in qs.filter(has_tag=True).values_list("pk", flat=True)
            )
        self.fields["unit_price"].required = False

        if is_birth:
            # Restrict mother selection to ACTIVE female/mixed animals owned by
            # this project, and default the birth date to today.
            if project is not None:
                self.fields["mother"].queryset = Product.objects.filter(
                    entity=project,
                    product_template__nature=ProductTemplate.Nature.ANIMAL,
                    product_template__gender__in=(
                        ProductTemplate.Gender.FEMALE,
                        ProductTemplate.Gender.MIXED,
                    ),
                ).select_related("product_template")
            if not self.fields["birth_date"].initial:
                self.fields["birth_date"].initial = date.today()
        else:
            # Remove the birth-only fields for non-birth operations (PURCHASE).
            for f in ("mother", "gender", "birth_date"):
                self.fields.pop(f, None)

    def clean(self):
        cleaned = super().clean()
        template = cleaned.get("product_template")
        uid = cleaned.get("unique_id", "").strip()

        # ── Birth flow ────────────────────────────────────────────────────
        if getattr(self, "is_birth", False):
            mother = cleaned.get("mother")
            if mother:
                # Ownership guard: never allow a mother owned by another project.
                if self.project is not None and mother.entity_id != self.project.id:
                    self.add_error(
                        "mother",
                        "Mother must belong to the same project.",
                    )
                    return cleaned
                # Default the newborn template to the mother's gives_birth_to
                # (e.g. Dairy Cow → Calf) unless the user picked another one.
                gbt_id = mother.product_template.gives_birth_to_id
                if gbt_id and (template is None or template.pk == mother.product_template_id):
                    template = cleaned["product_template"] = mother.product_template.gives_birth_to
                if not cleaned.get("birth_date"):
                    cleaned["birth_date"] = date.today()
                if template is None:
                    self.add_error(
                        "product_template",
                        "Newborn template is required (or select a mother whose "
                        "template has a 'gives birth to' template).",
                    )
                    return cleaned

        # If product is selected, require unit_price
        if template and not cleaned.get("unit_price"):
            self.add_error(
                "unit_price", "Unit price is required when a product is selected."
            )

        # Individual tracking: auto-suggest a unique tag when left blank, so
        # the user sees the suggestion and may edit it.  A bulk quantity is
        # allowed — the backend creates one tagged Product per head.
        if (
            template
            and template.tracking_mode == ProductTemplate.TrackingMode.INDIVIDUAL
        ):
            if not uid and self.project is not None:
                uid = template.next_tag(self.project)
                cleaned["unique_id"] = uid
            if not uid:
                self.add_error(
                    "unique_id",
                    "Tag / ID is required for individually tracked animals.",
                )

        if uid:
            # Friendly duplicate-tag message; the DB UniqueConstraint on
            # (entity, unique_id) is the hard backstop.
            qs = Product.objects.filter(unique_id=uid)
            if self.project is not None:
                qs = qs.filter(entity=self.project)
            if qs.exists():
                self.add_error(
                    "unique_id",
                    "This tag is already in use for this project.",
                )
        return cleaned


class BaseInvoiceItemCreateFormSet(forms.BaseInlineFormSet):
    """Passes `project` and `is_birth` down to each InvoiceItemCreateForm."""

    def __init__(self, *args, project=None, is_birth=False, **kwargs):
        self.project = project
        self.is_birth = is_birth
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["project"] = self.project
        kwargs["is_birth"] = self.is_birth
        return kwargs


InvoiceItemCreateFormSet = forms.inlineformset_factory(
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

    Pass ``entity`` (the owning project) to restrict the selectable products to
    those belonging to that entity — prevents moving another project's stock.
    """

    selected_product = forms.ModelChoiceField(
        queryset=Product.objects.select_related("product_template").all(),
        label="Animal / Product",
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
            "quantity": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm amount-input qty-input",
                    "step": "0.01",
                    "inputmode": "decimal",
                }
            ),
            "unit_price": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm amount-input price-input",
                    "step": "0.01",
                    "inputmode": "decimal",
                }
            ),
        }

    def __init__(self, *args, entity=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.entity = entity
        if entity is not None:
            self.fields["selected_product"].queryset = (
                Product.objects.filter(entity=entity).select_related("product_template")
            )

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("selected_product")
        if product:
            product.validate_active()
            # Ownership guard: never allow selecting a product owned by another
            # entity, even if a crafted request bypasses the filtered queryset.
            if self.entity is not None and product.entity_id != self.entity.id:
                from django.utils.translation import gettext as _

                self.add_error(
                    "selected_product",
                    _(
                        "Product '%(p)s' does not belong to '%(entity)s' and "
                        "cannot be used in this operation."
                    )
                    % {"p": product, "entity": self.entity},
                )
                return cleaned
            # Derive the required ProductTemplate FK from the selected Product
            self.instance.product_template = product.product_template
        return cleaned


class BaseInvoiceItemSelectFormSet(forms.BaseInlineFormSet):
    """Passes the owning ``entity`` down to each InvoiceItemSelectForm."""

    def __init__(self, *args, entity=None, **kwargs):
        self.entity = entity
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["entity"] = self.entity
        return kwargs


InvoiceItemSelectFormSet = forms.inlineformset_factory(
    Operation,
    InvoiceItem,
    form=InvoiceItemSelectForm,
    formset=BaseInvoiceItemSelectFormSet,
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
        label=_("Product"),
        empty_label="— select —",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    class Meta:
        model = InventoryMovementLine
        fields = ("invoice_item", "quantity", "group_key")
        widgets = {
            "quantity": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-sm amount-input",
                    "step": "0.01",
                    "placeholder": "0.00",
                    "inputmode": "decimal",
                }
            ),
            "group_key": forms.HiddenInput(),
        }

    def __init__(self, *args, operation=None, **kwargs):
        super().__init__(*args, **kwargs)
        if operation is not None:
            self.fields["invoice_item"].queryset = InvoiceItem.objects.filter(
                operation=operation
            ).select_related("product_template")
            # Pre-set the operation on the instance so model-level field
            # validation (non-nullable FK) doesn't reject it before the view
            # has a chance to assign line.operation after form validation.
            if self.instance.pk is None:
                self.instance.operation = operation


class BaseInventoryMovementLineFormSet(BaseModelFormSet):
    """
    Standalone model formset for InventoryMovementLine.

    Passes ``operation`` down to each form so the invoice_item dropdown is
    filtered to items belonging to the current operation.

    Auto-generates a ``group_key`` (a short hex string) that is applied to all
    newly created lines, allowing the UI to group lines that were created
    together in a single submission.
    """

    def __init__(self, *args, operation=None, **kwargs):
        self.operation = operation
        self.group_key = uuid.uuid4().hex[:8]  # shared key for this batch
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["operation"] = self.operation
        return kwargs

    def save_new(self, form, commit=True):
        """Set the ``group_key`` before persisting."""
        obj = form.save(commit=False)
        if not obj.group_key:
            obj.group_key = self.group_key
        if commit:
            obj.save()
        return obj


InventoryMovementLineFormSet = modelformset_factory(
    InventoryMovementLine,
    form=InventoryMovementLineForm,
    formset=BaseInventoryMovementLineFormSet,
    extra=1,
    can_delete=False,
)


# ---------------------------------------------------------------------------
# Deferred Movement Form – register movements for unmoved products
# A single form where the officer selects an invoice item, then enters the
# quantity to move. The backend creates the appropriate
# InventoryMovementLine records based on the template's tracking mode.
# ---------------------------------------------------------------------------


class DeferredMovementForm(LoggingFormMixin, forms.Form):
    """
    Register inventories movements for unmoved products on an operation.

    The officer picks an ``InvoiceItem`` from the operation and enters the
    quantity being moved.  The backend uses the product template's tracking
    mode to decide how many ``InventoryMovementLine`` records to create:
      - INDIVIDUAL → one ``InventoryMovementLine`` per product (qty=1 each)
      - BATCH/COMMODITY → one ``InventoryMovementLine`` with the full qty
    """

    invoice_item = forms.ModelChoiceField(
        queryset=InvoiceItem.objects.all(),
        label=_("Invoice Item"),
        empty_label="— select item —",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    quantity = forms.DecimalField(
        label=_("Quantity to move"),
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "placeholder": "0.00",
            }
        ),
    )
    notes = forms.CharField(
        label=_("Notes"),
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Optional notes"}
        ),
    )

    def __init__(self, *args, operation=None, **kwargs):
        super().__init__(*args, **kwargs)
        if operation is not None:
            self.fields["invoice_item"].queryset = InvoiceItem.objects.filter(
                operation=operation
            ).select_related("product_template")
