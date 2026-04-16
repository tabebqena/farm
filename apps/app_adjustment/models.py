from typing import List

from django.db import models
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.app_adjustment._effect import AdjustmentEffect
from apps.app_base.mixins import (
    AmountCleanMixin,
    ImmutableMixin,
    LinkedIssuanceTransactionMixin,
    OfficerMixin,
)
from apps.app_base.models import BaseModel, ReversableModel
from apps.app_operation.models.operation_type import OperationType
from apps.app_transaction.models import TransactionType


class AdjustmentType(models.TextChoices):
    # ==========================
    # PURCHASE ADJUSTMENTS (Our Debts)
    # ==========================

    # Reductions in what WE owe the Vendor
    PURCHASE_RETURN = "PUR_RET", _("Purchase: Return to Vendor (Credit)")
    PURCHASE_DISCOUNT = "PUR_DISC", _("Purchase: Post-Invoice Discount (Credit)")
    PURCHASE_OVERCHARGE = "PUR_OVER", _(
        "Purchase: Price Overcharge Correction (Credit)"
    )
    PURCHASE_SHORTAGE = "PUR_SHORT", _("Purchase: Quantity Shortage (Credit)")
    PURCHASE_DAMAGE = "PUR_DAM", _("Purchase: Damage Allowance (Credit)")
    PURCHASE_GENERAL_REDUCTION = (
        "PUR_G_RED",
        _("Purchase: Reduction of the amount of the purchase by a not mentioned cause"),
    )

    # Increases in what WE owe the Vendor
    PURCHASE_UNDERCHARGE = "PUR_UNDER", _(
        "Purchase: Price Undercharge Correction (Debit)"
    )
    PURCHASE_TAX_ADDITION = "PUR_TAX", _("Purchase: Tax Undercharge (Debit)")
    PURCHASE_FREIGHT = "PUR_FREIGHT", _("Purchase: Unbilled Freight (Debit)")
    PURCHASE_GENERAL_INCREASE = (
        "PUR_G_INC",
        _("Purchase: Increase of the amount of the purchase by a not mentioned cause"),
    )

    # ==========================
    # SALE ADJUSTMENTS (Their Debts)
    # ==========================

    # Reductions in what the CLIENT owes us
    SALE_RETURN = "SALE_RET", _("Sale: Return from Client (Credit)")
    SALE_DISCOUNT = "SALE_DISC", _("Sale: Post-Invoice Discount (Credit)")
    SALE_OVERCHARGE = "SALE_OVER", _("Sale: Price Overcharge Correction (Credit)")
    SALE_SHORTAGE = "SALE_SHORT", _("Sale: Quantity Shortage (Credit)")
    SALE_DAMAGE = "SALE_DAM", _("Sale: Damage Allowance (Credit)")
    SALE_WRITE_OFF = "SALE_WRITE", _("Sale: Bad Debt Write-off (Credit)")
    SALE_GENERAL_REDUCTION = (
        "SALE_G_RED",
        _("Sale: Reduction of the amount of the sale by a not mentioned cause"),
    )

    # Increases in what the CLIENT owes us
    SALE_UNDERCHARGE = "SALE_UNDER", _("Sale: Price Undercharge Correction (Debit)")
    SALE_TAX_ADDITION = "SALE_TAX", _("Sale: Tax Undercharge (Debit)")
    SALE_LATE_FEE = "SALE_FEE", _("Sale: Late Payment Penalty (Debit)")
    SALE_GENERAL_INCREASE = (
        "SALE_G_INC",
        _("Sale: Increase of the amount of the sale by a not mentioned cause"),
    )

    # ==========================
    # PROPERTIES
    # ==========================
    @classmethod
    def is_general(cls, tp):
        return tp in (
            AdjustmentType.PURCHASE_GENERAL_INCREASE,
            AdjustmentType.PURCHASE_GENERAL_REDUCTION,
            AdjustmentType.SALE_GENERAL_INCREASE,
            AdjustmentType.SALE_GENERAL_REDUCTION,
        )

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
            AdjustmentType.PURCHASE_GENERAL_REDUCTION,
            AdjustmentType.SALE_GENERAL_REDUCTION,
        )


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
        verbose_name=_("operation"),
    )
    type = models.CharField(_("type"), max_length=20, choices=AdjustmentType.choices)
    amount = models.DecimalField(_("amount"), max_digits=20, decimal_places=2)
    effect = models.CharField(
        _("effect"),
        max_length=10,
        choices=AdjustmentEffect.choices,
    )
    reason = models.TextField(_("reason"), blank=True)
    date = models.DateField(_("date"))
    officer = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="adjustments_supervised",
        verbose_name=_("officer"),
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
        if self.effect == AdjustmentEffect.INCREASE:
            return {
                OperationType.PURCHASE: TransactionType.PURCHASE_ADJUSTMENT_INCREASE,
                OperationType.SALE: TransactionType.SALE_ADJUSTMENT_INCREASE,
                OperationType.EXPENSE: TransactionType.EXPENSE_ADJUSTMENT_INCREASE,
            }.get(self.operation.operation_type)
        return {
            OperationType.PURCHASE: TransactionType.PURCHASE_ADJUSTMENT_DECREASE,
            OperationType.SALE: TransactionType.SALE_ADJUSTMENT_DECREASE,
            OperationType.EXPENSE: TransactionType.EXPENSE_ADJUSTMENT_DECREASE,
        }.get(self.operation.operation_type)

    def clean(self):
        if self.operation.operation_type not in (
            OperationType.PURCHASE,
            OperationType.SALE,
            OperationType.EXPENSE,
        ):
            raise ValidationError(_("This operation cannot be adjusted."))
        if AdjustmentType.is_general(self.type) and not self.reason:
            raise ValidationError(_("Reason is required in general adjustment types."))
        # Automatically set the effect before validation/save
        if AdjustmentType.is_reduction(self.type):
            self.effect = AdjustmentEffect.DECREASE
        else:
            self.effect = AdjustmentEffect.INCREASE
        return super().clean()

    @property
    def _reversable_transaction_types(self) -> List[TransactionType]:
        return [self._issuance_transaction_type]  # type: ignore

    @property
    def _implicit_reversable_transaction_types(self):
        return [self._issuance_transaction_type]  # type: ignore

    class Meta:
        verbose_name = _("adjustment")
        verbose_name_plural = _("adjustments")
