from app_base.models import BaseModel
from django.db import models
from django.forms import ValidationError


class InvoiceItem(BaseModel):
    invoice = models.ForeignKey(
        "Invoice", related_name="items", on_delete=models.CASCADE
    )
    product = models.ForeignKey(
        "app_inventory.InventoryItem", on_delete=models.PROTECT, related_name="invoices"
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
        "Operation", related_name="invoice", on_delete=models.CASCADE
    )
    description = models.TextField(blank=True)

    @property
    def total_price(self):
        raise NotImplementedError()

    def clean(self) -> None:
        from apps.app_operation.models.operation import OperationType

        if self.operation.operation_type not in (
            OperationType.PURCHASE,
            OperationType.SALE,
        ):
            raise ValidationError(
                f"This operation type {self.operation.operation_type} is not allowed to have invoice"
            )
        return super().clean()
