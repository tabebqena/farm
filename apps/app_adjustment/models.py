from app_base.mixins import (
    AmountCleanMixin,
    HasRelatedTransactions,
    ImmutableMixin,
    LinkedIssuanceTransactionMixin,
    OfficerMixin,
)
from apps.app_base.models import BaseModel
from django.db import models
from django.forms import ValidationError
from apps.app_transaction.models import TransactionType
from apps.app_operation.models import OperationType


class InvoiceAdjustmentType(models.TextChoices):
    # ==========================
    # PURCHASE ADJUSTMENTS (Our Debts)
    # ==========================

    # Reductions in what WE owe the Vendor
    PURCHASE_RETURN = "PUR_RET", "Purchase: Return to Vendor (Credit)"
    PURCHASE_DISCOUNT = "PUR_DISC", "Purchase: Post-Invoice Discount (Credit)"
    PURCHASE_OVERCHARGE = "PUR_OVER", "Purchase: Price Overcharge Correction (Credit)"
    PURCHASE_SHORTAGE = "PUR_SHORT", "Purchase: Quantity Shortage (Credit)"
    PURCHASE_DAMAGE = "PUR_DAM", "Purchase: Damage Allowance (Credit)"

    # Increases in what WE owe the Vendor
    PURCHASE_UNDERCHARGE = "PUR_UNDER", "Purchase: Price Undercharge Correction (Debit)"
    PURCHASE_TAX_ADDITION = "PUR_TAX", "Purchase: Tax Undercharge (Debit)"
    PURCHASE_FREIGHT = "PUR_FREIGHT", "Purchase: Unbilled Freight (Debit)"

    # ==========================
    # SALE ADJUSTMENTS (Their Debts)
    # ==========================

    # Reductions in what the CLIENT owes us
    SALE_RETURN = "SALE_RET", "Sale: Return from Client (Credit)"
    SALE_DISCOUNT = "SALE_DISC", "Sale: Post-Invoice Discount (Credit)"
    SALE_OVERCHARGE = "SALE_OVER", "Sale: Price Overcharge Correction (Credit)"
    SALE_SHORTAGE = "SALE_SHORT", "Sale: Quantity Shortage (Credit)"
    SALE_DAMAGE = "SALE_DAM", "Sale: Damage Allowance (Credit)"
    SALE_WRITE_OFF = "SALE_WRITE", "Sale: Bad Debt Write-off (Credit)"

    # Increases in what the CLIENT owes us
    SALE_UNDERCHARGE = "SALE_UNDER", "Sale: Price Undercharge Correction (Debit)"
    SALE_TAX_ADDITION = "SALE_TAX", "Sale: Tax Undercharge (Debit)"
    SALE_LATE_FEE = "SALE_FEE", "Sale: Late Payment Penalty (Debit)"

    # ==========================
    # PROPERTIES
    # ==========================

    @property
    def is_reduction(self):
        """Returns True if this type subtracts from the balance."""
        return self in (
            InvoiceAdjustmentType.PURCHASE_RETURN,
            InvoiceAdjustmentType.PURCHASE_DISCOUNT,
            InvoiceAdjustmentType.PURCHASE_OVERCHARGE,
            InvoiceAdjustmentType.PURCHASE_SHORTAGE,
            InvoiceAdjustmentType.PURCHASE_DAMAGE,
            InvoiceAdjustmentType.SALE_RETURN,
            InvoiceAdjustmentType.SALE_DISCOUNT,
            InvoiceAdjustmentType.SALE_OVERCHARGE,
            InvoiceAdjustmentType.SALE_SHORTAGE,
            InvoiceAdjustmentType.SALE_DAMAGE,
            InvoiceAdjustmentType.SALE_WRITE_OFF,
        )


class Adjustment(
    ImmutableMixin,
    AmountCleanMixin,
    OfficerMixin,
    LinkedIssuanceTransactionMixin,
    BaseModel,
):
    _immutable_fields = {
        "operation": {},
        "type": {},
        "amount": {},
        "effect": {},
    }
    _amount_name = "amount"
    operation = models.ForeignKey(
        "app_operation.Operation",
        on_delete=models.PROTECT,
        related_name="adjustments",
    )
    type = models.CharField(max_length=20, choices=InvoiceAdjustmentType.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    effect = models.CharField(
        max_length=10,
        choices=[("INCREASE", "Increase"), ("DECREASE", "Decrease")],
    )
    reason = models.TextField()
    date = models.DateField()
    officer = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="adjustments_supervised",
    )

    @property
    def payment_source_fund(self):
        return self.operation.payment_source_fund

    @property
    def payment_target_fund(self):
        return self.operation.payment_target_fund

    @property
    def _issuance_transaction_type(self):
        return {
            OperationType.PURCHASE: TransactionType.PURCHASE_ADJUSTMENT,
            OperationType.SALE: TransactionType.SALE_ADJUSTMENT,
            OperationType.EXPENSE: TransactionType.EXPENSE_ADJUSTMENT,
        }.get(self.operation.operation_type)

    def clean(self):
        if OperationType._is_one_shot_operation(self.operation.operation_type):
            raise ValidationError(
                "One-shot operations cannot be adjusted. Please reverse and redo instead."
            )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
