from decimal import Decimal

from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.app_base.mixins import AmountCleanMixin
from apps.app_base.models import BaseModel


class ProductTemplate(BaseModel):
    class TrackingMode(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", _("Individual (Tag ID)")
        BATCH = "BATCH", _("Batch/Group")
        COMMODITY = "COMMODITY", _("Quantity (Weight/Volume)")

    class Nature(models.TextChoices):
        ANIMAL = "ANIMAL", _("Livestock Asset")
        FEED = "FEED", _("Consumable")
        MEDICINE = "MEDICINE", _("Biological")
        PRODUCT = "PRODUCT", _("Production Output")

    name = models.CharField(_("name"), max_length=100)  # e.g., "Fattening Calves"
    name_ar = models.CharField(_("name (Arabic)"), max_length=100, blank=True)
    nature = models.CharField(
        _("nature"), choices=Nature.choices, max_length=20, default=Nature.ANIMAL
    )
    default_unit = models.CharField(
        _("default unit"), max_length=20, default="Head"
    )  # e.g., "Head", "Kg"
    requires_individual_tag = models.BooleanField(
        _("requires individual tag"), default=False
    )

    tracking_mode = models.CharField(
        _("tracking mode"),
        choices=TrackingMode.choices,
        max_length=24,
        default=TrackingMode.BATCH,
    )

    entities = models.ManyToManyField(
        "app_entity.Entity",
        related_name="product_templates",
        verbose_name=_("entities"),
        blank=True,
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("product template")
        verbose_name_plural = _("product templates")


class InvoiceItem(AmountCleanMixin, BaseModel):
    _amount_name = "quantity"

    invoice = models.ForeignKey(
        "Invoice",
        related_name="items",
        on_delete=models.CASCADE,
        verbose_name=_("invoice"),
    )
    product = models.ForeignKey(
        ProductTemplate,
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name=_("product"),
    )
    description = models.TextField(_("description"), blank=True)
    quantity = models.DecimalField(
        _("quantity"), max_digits=10, decimal_places=2, default=1
    )
    unit_price = models.DecimalField(_("unit price"), max_digits=15, decimal_places=2)

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    def clean_unit_price(self):
        if self.unit_price < 0:
            raise ValidationError(_("Unit price cannot be negative"))

    class Meta:
        verbose_name = _("invoice item")
        verbose_name_plural = _("invoice items")


class Invoice(BaseModel):
    # Direction of goods (who gave vs. received InvoiceItems) is not
    # encoded in source/destination field names alone — it depends on
    # operation_type (e.g. PURCHASE vs. SALE).
    operation = models.OneToOneField(
        "app_operation.Operation",
        related_name="invoice",
        on_delete=models.CASCADE,
        verbose_name=_("operation"),
    )
    description = models.TextField(_("description"), blank=True)

    @property
    def total_price(self):
        result = self.items.aggregate(
            total=Sum(
                ExpressionWrapper(
                    F("quantity") * F("unit_price"),
                    output_field=DecimalField(max_digits=15, decimal_places=2),
                )
            )
        )
        return result["total"] or Decimal("0.00")

    def clean(self) -> None:
        from apps.app_operation.models.operation_type import OperationType

        if self.operation.operation_type not in (
            OperationType.PURCHASE,
            OperationType.SALE,
            OperationType.CAPITAL_GAIN,
            OperationType.CAPITAL_LOSS,
            OperationType.BIRTH,
            OperationType.DEATH,
        ):
            raise ValidationError(
                _("This operation type %(op_type)s is not allowed to have invoice")
                % {"op_type": self.operation.operation_type}
            )
        return super().clean()

    class Meta:
        verbose_name = _("invoice")
        verbose_name_plural = _("invoices")


class Product(AmountCleanMixin, BaseModel):
    _amount_name = "unit_price"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Active")
        SOLD = "SOLD", _("Sold")
        DEAD = "DEAD", _("Dead")

    product_template = models.ForeignKey(
        ProductTemplate, on_delete=models.PROTECT, verbose_name=_("product template")
    )
    invoice_items = models.ManyToManyField(
        InvoiceItem, related_name="products", verbose_name=_("invoice items")
    )
    unique_id = models.CharField(
        _("unique id"), max_length=50, db_index=True, null=True, blank=True
    )
    quantity = models.PositiveIntegerField(_("quantity"), default=1)
    unit_price = models.DecimalField(_("unit price"), max_digits=15, decimal_places=2)
    notes = models.TextField(_("notes"), blank=True)

    @property
    def status(self) -> str:
        from apps.app_operation.models.operation_type import OperationType

        types = set(
            self.invoice_items.values_list(
                "invoice__operation__operation_type", flat=True
            )
        )
        if OperationType.DEATH in types:
            return self.Status.DEAD
        if OperationType.SALE in types:
            return self.Status.SOLD
        return self.Status.ACTIVE

    @property
    def current_value(self) -> Decimal:
        from apps.app_operation.models.operation_type import OperationType

        base = self.unit_price * self.quantity

        def _sum(op_type):
            result = self.invoice_items.filter(
                invoice__operation__operation_type=op_type
            ).aggregate(
                total=Sum(
                    ExpressionWrapper(
                        F("quantity") * F("unit_price"),
                        output_field=DecimalField(max_digits=15, decimal_places=2),
                    )
                )
            )
            return result["total"] or Decimal("0.00")

        return (
            base + _sum(OperationType.CAPITAL_GAIN) - _sum(OperationType.CAPITAL_LOSS)
        )

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
