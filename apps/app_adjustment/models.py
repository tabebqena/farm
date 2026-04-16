from decimal import Decimal
from typing import List

from django.conf import settings
from django.db import models, transaction as db_transaction
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.app_adjustment._effect import AdjustmentEffect
from apps.app_adjustment._item_type import InvoiceItemAdjustmentType
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
    # INVOICE ITEM CORRECTIONS
    # ==========================
    PURCHASE_ITEM_CORRECTION = "PUR_ITEM", _("Purchase: Invoice Item Correction")
    SALE_ITEM_CORRECTION = "SALE_ITEM", _("Sale: Invoice Item Correction")

    # ==========================
    # PROPERTIES
    # ==========================
    @classmethod
    def is_item_correction(cls, tp):
        return tp in (
            AdjustmentType.PURCHASE_ITEM_CORRECTION,
            AdjustmentType.SALE_ITEM_CORRECTION,
        )

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
        """Returns True if this type subtracts from the balance.

        Item-correction types are excluded — their effect is determined at
        runtime by the sign of the net delta in InvoiceItemAdjustment.finalize().
        """
        if cls.is_item_correction(tp):
            return False
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
        blank=True,
    )
    reason = models.TextField(_("reason"), blank=True)
    date = models.DateField(_("date"))
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
        # Automatically set the effect before validation/save.
        # Item-correction types have their effect pre-set by
        # InvoiceItemAdjustment.finalize(), so we leave it untouched.
        if not AdjustmentType.is_item_correction(self.type):
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


# ---------------------------------------------------------------------------
# InvoiceItem-basis adjustment
# ---------------------------------------------------------------------------


class InvoiceItemAdjustment(
    ImmutableMixin,
    OfficerMixin,
    ReversableModel,
    BaseModel,
):
    """
    Records a correction to one or more InvoiceItems on a PURCHASE or SALE.

    Responsibilities:
    - Owns the line-level change records (InvoiceItemAdjustmentLine).
    - Syncs ProductLedgerEntry for each line via the line's save().
    - Delegates financial bookkeeping by creating an Adjustment in finalize().
    """

    _immutable_fields = {
        "operation": {},
        "type": {},
    }

    operation = models.ForeignKey(
        "app_operation.Operation",
        on_delete=models.PROTECT,
        related_name="item_adjustments",
        verbose_name=_("operation"),
    )
    # Populated by finalize() after all lines are saved.
    adjustment = models.OneToOneField(
        Adjustment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="item_adjustment",
        verbose_name=_("accounting adjustment"),
    )
    type = models.CharField(
        _("type"), max_length=20, choices=InvoiceItemAdjustmentType.choices
    )
    reason = models.TextField(_("reason"), blank=True)
    date = models.DateField(_("date"))
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="item_adjustments_supervised",
        verbose_name=_("officer"),
    )

    def clean(self):
        if self.operation.operation_type not in (
            OperationType.PURCHASE,
            OperationType.SALE,
        ):
            raise ValidationError(
                _("Invoice item adjustments are only allowed on Purchase or Sale operations.")
            )
        # Validate type matches operation
        purchase_types = (
            InvoiceItemAdjustmentType.PURCHASE_ITEM_INCREASE,
            InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE,
        )
        sale_types = (
            InvoiceItemAdjustmentType.SALE_ITEM_INCREASE,
            InvoiceItemAdjustmentType.SALE_ITEM_DECREASE,
        )
        if self.operation.operation_type == OperationType.PURCHASE and self.type not in purchase_types:
            raise ValidationError(_("Use a PURCHASE_ITEM_* type for Purchase operations."))
        if self.operation.operation_type == OperationType.SALE and self.type not in sale_types:
            raise ValidationError(_("Use a SALE_ITEM_* type for Sale operations."))
        return super().clean()

    def _reverse_adjustment(self):
        """Reversal records must not copy the OneToOneField — they have no
        accounting Adjustment of their own (the counter-transaction lives on
        the reversed Adjustment)."""
        return None

    def finalize(self):
        """
        Compute the net delta from all lines, create the accounting Adjustment,
        and link it back. Must be called inside an atomic block, after all lines
        have been saved.
        """
        if self.adjustment_id is not None:
            raise ValidationError(_("This item adjustment has already been finalized."))

        total_delta = sum(line.value_delta for line in self.lines.all())
        if total_delta == 0:
            raise ValidationError(_("Net adjustment is zero — nothing to record."))

        adj_type_map = {
            InvoiceItemAdjustmentType.PURCHASE_ITEM_INCREASE: AdjustmentType.PURCHASE_ITEM_CORRECTION,
            InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE: AdjustmentType.PURCHASE_ITEM_CORRECTION,
            InvoiceItemAdjustmentType.SALE_ITEM_INCREASE: AdjustmentType.SALE_ITEM_CORRECTION,
            InvoiceItemAdjustmentType.SALE_ITEM_DECREASE: AdjustmentType.SALE_ITEM_CORRECTION,
        }
        effect = AdjustmentEffect.INCREASE if total_delta > 0 else AdjustmentEffect.DECREASE

        adj = Adjustment(
            operation=self.operation,
            type=adj_type_map[self.type],
            amount=abs(total_delta).quantize(Decimal("0.01")),
            effect=effect,
            reason=self.reason,
            date=self.date,
            officer=self.officer,
        )
        adj.full_clean()
        adj.save()  # creates issuance transaction via LinkedIssuanceTransactionMixin

        self.adjustment = adj
        self.save(update_fields=["adjustment"])

    def reverse(self, officer, date, reason=""):
        """
        Reverse the item adjustment:
        1. Reverse the linked Adjustment (counter-transaction).
        2. Append negating ProductLedgerEntry rows for each line.
        3. Mark this record as reversed via ReversableModel.
        """
        from apps.app_inventory.models import ProductLedgerEntry

        if self.adjustment is None:
            raise ValidationError(_("Cannot reverse an un-finalized item adjustment."))

        with db_transaction.atomic():
            self.adjustment.reverse(officer=officer, date=date, reason=reason)
            for line in self.lines.all():
                ProductLedgerEntry.record_adjustment_line(line, negate=True)
            return super().reverse(officer=officer, date=date, reason=reason)

    class Meta:
        verbose_name = _("invoice item adjustment")
        verbose_name_plural = _("invoice item adjustments")


class InvoiceItemAdjustmentLine(
    ImmutableMixin,
    BaseModel,
):
    """
    One line of an InvoiceItemAdjustment.

    Records how a single InvoiceItem was changed: price, quantity, or removal.
    On save, appends a ProductLedgerEntry row for the inventory delta.
    """

    _immutable_fields = {
        "adjustment": {},
        "invoice_item": {},
        "new_quantity": {},
        "new_unit_price": {},
        "is_removed": {},
    }

    adjustment = models.ForeignKey(
        InvoiceItemAdjustment,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("item adjustment"),
    )
    invoice_item = models.ForeignKey(
        "app_inventory.InvoiceItem",
        on_delete=models.PROTECT,
        related_name="item_adjustment_lines",
        verbose_name=_("invoice item"),
    )
    new_quantity = models.DecimalField(
        _("new quantity"), max_digits=10, decimal_places=2, null=True, blank=True
    )
    new_unit_price = models.DecimalField(
        _("new unit price"), max_digits=15, decimal_places=2, null=True, blank=True
    )
    is_removed = models.BooleanField(_("is removed"), default=False)

    @property
    def quantity_delta(self) -> Decimal:
        original = self.invoice_item.quantity
        if self.is_removed:
            return -original
        if self.new_quantity is not None:
            return self.new_quantity - original
        return Decimal("0")

    @property
    def value_delta(self) -> Decimal:
        """Positive = invoice total increased; negative = decreased."""
        item = self.invoice_item
        if self.is_removed:
            return -(item.total_price)
        new_qty = self.new_quantity if self.new_quantity is not None else item.quantity
        new_price = self.new_unit_price if self.new_unit_price is not None else item.unit_price
        return (new_qty * new_price) - item.total_price

    def clean(self):
        if not self.is_removed and self.new_quantity is None and self.new_unit_price is None:
            raise ValidationError(
                _("At least one of new_quantity, new_unit_price, or is_removed must be set.")
            )
        # Ensure the item belongs to the same operation
        try:
            item_op = self.invoice_item.invoice.operation
        except Exception:
            item_op = None
        if item_op is not None and item_op != self.adjustment.operation:
            raise ValidationError(
                _("The invoice item does not belong to the adjustment's operation.")
            )
        return super().clean()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from apps.app_inventory.models import ProductLedgerEntry
        ProductLedgerEntry.record_adjustment_line(self)

    class Meta:
        verbose_name = _("invoice item adjustment line")
        verbose_name_plural = _("invoice item adjustment lines")
