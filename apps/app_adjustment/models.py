import logging
from decimal import Decimal
from typing import List

from django.conf import settings
from django.db import models
from django.db import transaction as db_transaction
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.app_adjustment._item_type import InvoiceItemAdjustmentType
from apps.app_base.debug import DebugContext, debug_model_save
from apps.app_base.mixins import (
    AmountCleanMixin,
    ImmutableMixin,
    LinkedIssuanceTransactionMixin,
    OfficerMixin,
)
from apps.app_base.models import BaseModel, ReversableModel
from apps.app_operation.models.operation_type import OperationType
from apps.app_transaction.models import TransactionType

logger = logging.getLogger(__name__)


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
    # EXPENSE ADJUSTMENTS
    # ==========================
    EXPENSE_GENERAL_INCREASE = "EXP_G_INC", _("Expense: Increase")
    EXPENSE_GENERAL_REDUCTION = "EXP_G_RED", _("Expense: Decrease")

    # ==========================
    # INVOICE ITEM CORRECTIONS
    # ==========================
    PURCHASE_ITEM_CORRECTION_INCREASE = "PUR_ITEM_INC", _(
        "Purchase: Invoice Item Correction (Increase)"
    )
    PURCHASE_ITEM_CORRECTION_DECREASE = "PUR_ITEM_DEC", _(
        "Purchase: Invoice Item Correction (Decrease)"
    )
    SALE_ITEM_CORRECTION_INCREASE = "SALE_ITEM_INC", _(
        "Sale: Invoice Item Correction (Increase)"
    )
    SALE_ITEM_CORRECTION_DECREASE = "SALE_ITEM_DEC", _(
        "Sale: Invoice Item Correction (Decrease)"
    )

    # ==========================
    # PROPERTIES
    # ==========================
    @classmethod
    def is_item_correction(cls, tp):
        return tp in (
            AdjustmentType.PURCHASE_ITEM_CORRECTION_INCREASE,
            AdjustmentType.PURCHASE_ITEM_CORRECTION_DECREASE,
            AdjustmentType.SALE_ITEM_CORRECTION_INCREASE,
            AdjustmentType.SALE_ITEM_CORRECTION_DECREASE,
        )

    @classmethod
    def is_general(cls, tp):
        return tp in (
            AdjustmentType.PURCHASE_GENERAL_INCREASE,
            AdjustmentType.PURCHASE_GENERAL_REDUCTION,
            AdjustmentType.SALE_GENERAL_INCREASE,
            AdjustmentType.SALE_GENERAL_REDUCTION,
            AdjustmentType.EXPENSE_GENERAL_INCREASE,
            AdjustmentType.EXPENSE_GENERAL_REDUCTION,
        )

    @classmethod
    def is_reduction(cls, tp):
        """Returns True if this type flows in the reversed direction (target pays source).

        Direction encodes the effect: reduction types flip source↔target relative to
        the parent operation so that source always pays target — consistent with all
        other operation types.
        """
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
            AdjustmentType.EXPENSE_GENERAL_REDUCTION,
            AdjustmentType.PURCHASE_ITEM_CORRECTION_DECREASE,
            AdjustmentType.SALE_ITEM_CORRECTION_DECREASE,
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
    reason = models.TextField(_("reason"), blank=True)
    date = models.DateField(_("date"))
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="adjustments_supervised",
        verbose_name=_("officer"),
    )

    # Direction determines the effect: reduction types flow in the reversed direction
    # (operation's target pays operation's source), increases flow normally.
    # Source always pays target — consistent with all other operation types.
    @property
    def payment_source_fund(self):
        if AdjustmentType.is_reduction(self.type):
            return self.operation.payment_target_fund
        return self.operation.payment_source_fund

    @property
    def payment_target_fund(self):
        if AdjustmentType.is_reduction(self.type):
            return self.operation.payment_source_fund
        return self.operation.payment_target_fund

    @property
    def _issuance_transaction_type(self):
        if AdjustmentType.is_reduction(self.type):
            return {
                OperationType.PURCHASE: TransactionType.PURCHASE_ADJUSTMENT_DECREASE,
                OperationType.SALE: TransactionType.SALE_ADJUSTMENT_DECREASE,
                OperationType.EXPENSE: TransactionType.EXPENSE_ADJUSTMENT_DECREASE,
            }.get(self.operation.operation_type)
        return {
            OperationType.PURCHASE: TransactionType.PURCHASE_ADJUSTMENT_INCREASE,
            OperationType.SALE: TransactionType.SALE_ADJUSTMENT_INCREASE,
            OperationType.EXPENSE: TransactionType.EXPENSE_ADJUSTMENT_INCREASE,
        }.get(self.operation.operation_type)

    def clean(self):
        DebugContext.log(f"Adjustment.clean() for operation {self.operation.pk}", {
            "type": self.type,
            "operation_type": self.operation.operation_type,
            "amount": float(self.amount),
        })
        if self.operation.operation_type not in (
            OperationType.PURCHASE,
            OperationType.SALE,
            OperationType.EXPENSE,
        ):
            DebugContext.error("Invalid operation type for adjustment", data={
                "operation_type": self.operation.operation_type,
                "allowed": ["PURCHASE", "SALE", "EXPENSE"],
            })
            raise ValidationError(_("This operation cannot be adjusted."))
        if AdjustmentType.is_general(self.type) and not self.reason:
            DebugContext.warn("General adjustment type requires reason", {
                "type": self.type,
            })
            raise ValidationError(_("Reason is required in general adjustment types."))
        DebugContext.success("Adjustment validation passed")
        return super().clean()

    def save(self, *args, **kwargs):
        """Save adjustment with audit logging."""
        is_new = self.pk is None
        action = "created" if is_new else "updated"
        with DebugContext.section(f"Adjustment.save() ({action})", {
            "operation": str(self.operation),
            "type": self.type,
            "amount": float(self.amount),
        }):
            result = super().save(*args, **kwargs)
            DebugContext.success(f"Adjustment {action}", {"pk": self.pk})

            DebugContext.audit(
                action=f"adjustment_{action}",
                entity_type="Adjustment",
                entity_id=self.pk,
                details={
                    "operation": str(self.operation),
                    "type": self.type,
                    "amount": float(self.amount),
                },
                user=str(self.officer)
            )
            return result

    def delete(self, *args, **kwargs):
        """Delete adjustment with audit logging."""
        with DebugContext.section("Adjustment.delete()", {
            "pk": self.pk,
            "operation": str(self.operation),
            "type": self.type,
            "amount": float(self.amount),
        }):
            DebugContext.warn("Deleting adjustment", {
                "operation": str(self.operation),
                "type": self.type,
            })

            DebugContext.audit(
                action="adjustment_deleted",
                entity_type="Adjustment",
                entity_id=self.pk,
                details={
                    "operation": str(self.operation),
                    "type": self.type,
                },
                user=str(self.officer)
            )

            return super().delete(*args, **kwargs)

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
                _(
                    "Invoice item adjustments are only allowed on Purchase or Sale operations."
                )
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
        if (
            self.operation.operation_type == OperationType.PURCHASE
            and self.type not in purchase_types
        ):
            raise ValidationError(
                _("Use a PURCHASE_ITEM_* type for Purchase operations.")
            )
        if (
            self.operation.operation_type == OperationType.SALE
            and self.type not in sale_types
        ):
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
        DebugContext.log(f"InvoiceItemAdjustment.finalize() called", {
            "item_adjustment_pk": self.pk,
            "type": self.type,
            "operation_pk": self.operation.pk,
        })

        if self.adjustment_id is not None:
            DebugContext.error("Item adjustment already finalized", data={
                "item_adjustment_pk": self.pk,
                "adjustment_pk": self.adjustment_id,
            })
            raise ValidationError(_("This item adjustment has already been finalized."))

        lines = self.lines.all()
        DebugContext.log(f"Computing net delta from {lines.count()} lines", {
            "line_count": lines.count(),
        })

        total_delta = sum(line.value_delta for line in lines)
        DebugContext.log(f"Net delta computed", {
            "total_delta": float(total_delta),
            "is_increase": total_delta > 0,
        })

        if total_delta == 0:
            DebugContext.error("Net adjustment is zero", {
                "line_count": lines.count(),
            })
            raise ValidationError(_("Net adjustment is zero — nothing to record."))

        # Direction (increase vs decrease) is encoded in the type, not an effect field.
        # The sign of the net delta determines which direction type to use.
        is_increase = total_delta > 0
        adj_type_map = {
            InvoiceItemAdjustmentType.PURCHASE_ITEM_INCREASE: (
                AdjustmentType.PURCHASE_ITEM_CORRECTION_INCREASE
                if is_increase
                else AdjustmentType.PURCHASE_ITEM_CORRECTION_DECREASE
            ),
            InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE: (
                AdjustmentType.PURCHASE_ITEM_CORRECTION_INCREASE
                if is_increase
                else AdjustmentType.PURCHASE_ITEM_CORRECTION_DECREASE
            ),
            InvoiceItemAdjustmentType.SALE_ITEM_INCREASE: (
                AdjustmentType.SALE_ITEM_CORRECTION_INCREASE
                if is_increase
                else AdjustmentType.SALE_ITEM_CORRECTION_DECREASE
            ),
            InvoiceItemAdjustmentType.SALE_ITEM_DECREASE: (
                AdjustmentType.SALE_ITEM_CORRECTION_INCREASE
                if is_increase
                else AdjustmentType.SALE_ITEM_CORRECTION_DECREASE
            ),
        }

        adj_type = adj_type_map[self.type]
        DebugContext.log(f"Adjustment type mapped", {
            "input_type": self.type,
            "output_type": adj_type,
            "is_increase": is_increase,
        })

        with DebugContext.section(f"Creating Adjustment record", {
            "type": adj_type,
            "amount": float(abs(total_delta)),
            "operation_pk": self.operation.pk,
        }):
            adj = Adjustment(
                operation=self.operation,
                type=adj_type,
                amount=abs(total_delta).quantize(Decimal("0.01")),
                reason=self.reason,
                date=self.date,
                officer=self.officer,
            )
            adj.full_clean()
            DebugContext.log("Adjustment validation passed")
            adj.save()  # creates issuance transaction via LinkedIssuanceTransactionMixin
            DebugContext.success("Adjustment saved", {"adjustment_pk": adj.pk})

        self.adjustment = adj
        self.save(update_fields=["adjustment"])
        DebugContext.success("InvoiceItemAdjustment finalized", {
            "item_adjustment_pk": self.pk,
            "adjustment_pk": adj.pk,
        })

    def reverse(self, officer, date, reason=""):
        """
        Reverse the item adjustment:
        1. Reverse the linked Adjustment (counter-transaction).
        2. Append negating ProductLedgerEntry rows for each line.
        3. Mark this record as reversed via ReversableModel.
        """
        from apps.app_inventory.models import ProductLedgerEntry

        DebugContext.log(f"InvoiceItemAdjustment.reverse() called", {
            "item_adjustment_pk": self.pk,
            "adjustment_pk": self.adjustment_id,
            "officer": str(officer),
            "date": str(date),
        })

        if self.adjustment is None:
            DebugContext.error("Cannot reverse un-finalized item adjustment", data={
                "item_adjustment_pk": self.pk,
            })
            raise ValidationError(_("Cannot reverse an un-finalized item adjustment."))

        with DebugContext.section(f"Reversing InvoiceItemAdjustment", {
            "item_adjustment_pk": self.pk,
            "line_count": self.lines.count(),
        }):
            with db_transaction.atomic():
                DebugContext.log("Reversing linked Adjustment")
                self.adjustment.reverse(officer=officer, date=date, reason=reason)
                DebugContext.success("Linked Adjustment reversed")

                DebugContext.log("Recording negating ProductLedgerEntry rows")
                for line in self.lines.all():
                    ProductLedgerEntry.record_adjustment_line(line, negate=True)
                DebugContext.success(f"Negated ledger entries recorded")

                result = super().reverse(officer=officer, date=date, reason=reason)
                DebugContext.success("InvoiceItemAdjustment reversed successfully")
                return result

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
        new_price = (
            self.new_unit_price if self.new_unit_price is not None else item.unit_price
        )
        return (new_qty * new_price) - item.total_price

    def clean(self):
        if (
            not self.is_removed
            and self.new_quantity is None
            and self.new_unit_price is None
        ):
            raise ValidationError(
                _(
                    "At least one of new_quantity, new_unit_price, or is_removed must be set."
                )
            )
        # Ensure the item belongs to the same operation
        try:
            item_op = self.invoice_item.operation
        except Exception:
            item_op = None
        if item_op is not None and item_op != self.adjustment.operation:
            raise ValidationError(
                _("The invoice item does not belong to the adjustment's operation.")
            )
        return super().clean()

    def save(self, *args, **kwargs):
        DebugContext.log(f"InvoiceItemAdjustmentLine.save()", {
            "pk": self.pk,
            "adjustment_pk": self.adjustment_id,
            "invoice_item_pk": self.invoice_item_id,
            "is_removed": self.is_removed,
            "quantity_delta": float(self.quantity_delta) if self.quantity_delta else None,
            "value_delta": float(self.value_delta) if self.value_delta else None,
        })
        super().save(*args, **kwargs)
        from apps.app_inventory.models import ProductLedgerEntry

        DebugContext.log("Recording ProductLedgerEntry for adjustment line")
        ProductLedgerEntry.record_adjustment_line(self)
        DebugContext.success("ProductLedgerEntry recorded", {"adjustment_line_pk": self.pk})

    class Meta:
        verbose_name = _("invoice item adjustment line")
        verbose_name_plural = _("invoice item adjustment lines")
