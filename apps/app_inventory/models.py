from django.db import models
from django.forms import ValidationError

from apps.app_base.models import BaseModel


class Category(BaseModel):
    class Nature(models.TextChoices):
        ANIMAL = "ANIMAL", "Livestock Asset"
        FEED = "FEED", "Consumable"
        MEDICINE = "MEDICINE", "Biological"
        PRODUCT = "PRODUCT", "Production Output"

    name = models.CharField(max_length=100)  # e.g., "Fattening Calves"
    nature = models.CharField(choices=Nature.choices, max_length=20)
    default_unit = models.CharField(max_length=20)  # e.g., "Head", "Kg"
    requires_individual_tag = models.BooleanField(default=False)


class Product(BaseModel):
    class TrackingMode(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "Individual (Tag ID)"
        BATCH = "BATCH", "Batch/Group"
        COMMODITY = "COMMODITY", "Quantity (Weight/Volume)"

    name = models.CharField(max_length=255)  # e.g. "Angus Cow #405" or "Batch #12"
    category = models.ForeignKey(Category, on_delete=models.PROTECT)  # e.g. "Cattle"
    tracking_mode = models.CharField(choices=TrackingMode.choices)

    # Livestock-specific fields
    # birth_date = models.DateField(null=True)
    # initial_weight = models.DecimalField(...)


class InvoiceItem(BaseModel):
    invoice = models.ForeignKey(
        "Invoice", related_name="items", on_delete=models.CASCADE
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="invoices"
    )
    description = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Optional: You can add logic here to sync the total
        # of all items back to the parent Operation's amount field.


class Invoice(BaseModel):
    operation = models.ForeignKey(
        "app_operation.Operation", related_name="invoice", on_delete=models.CASCADE
    )
    description = models.TextField(blank=True)

    @property
    def total_price(self):
        raise NotImplementedError()

    def clean(self) -> None:
        from apps.app_operation.models.operation_type import OperationType

        if self.operation.operation_type not in (
            OperationType.PURCHASE,
            OperationType.SALE,
        ):
            raise ValidationError(
                f"This operation type {self.operation.operation_type} is not allowed to have invoice"
            )
        return super().clean()


class ProductEvaluation(BaseModel):
    product = models.ForeignKey(
        "aap_inventory.Product", on_delete=models.CASCADE, related_name="evaluations"
    )

    price = models.DecimalField(max_digits=15, decimal_places=2)
    # Metadata for Bonuses
    evaluator = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.SET_NULL,
        null=True,
    )
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
