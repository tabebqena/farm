from typing import List

from django.db import models
from django.forms import ValidationError

from apps.app_base.mixins import (
    AmountCleanMixin,
    ImmutableMixin,
    LinkedIssuanceTransactionMixin,
    OfficerMixin,
)
from apps.app_base.models import BaseModel, ReversableModel
from apps.app_operation.models import OperationType
from apps.app_transaction.models import TransactionType


class AdjustmentType(models.TextChoices):
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

    @classmethod
    def is_reduction(cls, tp):
        """Returns True if this type subtracts from the balance."""
        return tp in (
            AdjustmentType.PURCHASE_RETURN,
            AdjustmentType.PURCHASE_DISCOUNT,
            AdjustmentType.PURCHASE_OVERCHARGE,
            AdjustmentType.PURCHASE_SHORTAGE,
            AdjustmentType.PURCHASE_DAMAGE,
            AdjustmentType.SALE_RETURN,
            AdjustmentType.SALE_DISCOUNT,
            AdjustmentType.SALE_OVERCHARGE,
            AdjustmentType.SALE_SHORTAGE,
            AdjustmentType.SALE_DAMAGE,
            AdjustmentType.SALE_WRITE_OFF,
        )


class AdjustmentEffect(models.TextChoices):
    INCREASE = "INCREASE", "Increase Original Amount"
    DECREASE = "DECREASE", "Decrease Original Amount"


class Adjustment(
    ImmutableMixin,
    AmountCleanMixin,
    OfficerMixin,
    LinkedIssuanceTransactionMixin,
    ReversableModel,
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
    type = models.CharField(max_length=20, choices=AdjustmentType.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    effect = models.CharField(
        max_length=10,
        choices=AdjustmentEffect.choices,
    )
    reason = models.TextField()
    date = models.DateField()
    officer = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="adjustments_supervised",
    )

    # We create another transaction in the same direction, but with
    # a modifierv effect.
    # So, the payment source & target fund are the same of the original operation.
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
        if self.operation.operation_type not in (
            OperationType.PURCHASE,
            OperationType.SALE,
            OperationType.EXPENSE,
        ):
            raise ValidationError("This operation cannot be adjusted.")
        if OperationType._is_one_shot_operation(self.operation.operation_type):
            raise ValidationError(
                "One-shot operations cannot be adjusted. Please reverse and redo instead."
            )

        return super().clean()

    def save(self, *args, **kwargs):
        # 2. Automatically set the effect before validation/save
        if AdjustmentType.is_reduction(self.type):
            self.effect = Adjustment.DECREASE
        else:
            self.effect = AdjustmentEffect.INCREASE
        return super().save(*args, **kwargs)

    @property
    def _reversable_transaction_types(self) -> List[TransactionType]:
        return [self._issuance_transaction_type]  # type: ignore

    @property
    def _implicit_reversable_transaction_types(self):
        return [self._issuance_transaction_type]  # type: ignore
