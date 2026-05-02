from datetime import date as date_type
from decimal import Decimal
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum

from apps.app_base.mixins import ImmutableMixin
from apps.app_base.models import BaseModel


class FinancialPeriod(ImmutableMixin, BaseModel):
    """
    An accounting period for one entity.
    Interval semantics: [start_date, end_date) — start_date is included, end_date is excluded.
    Periods are sequential and non-overlapping per entity.
    A period is "open" while end_date is None or end_date is in the future; it becomes
    "closed" once end_date is set AND end_date is before today.
    Once set, end_date cannot be changed (enforced by ImmutableMixin ALLOW_SET logic).
    amount records the profit (>0) or loss (<0) for this period once finalised.
    amount can be set once (from None) on a closed project period; it is then immutable.
    """

    _immutable_fields = {
        "entity": {},
        "start_date": {},
        "end_date": {"ALLOW_SET": True, "NULL_VALUES": (None,)},
        "amount": {"ALLOW_SET": True, "NULL_VALUES": (None,)},
    }

    entity = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="financial_periods",
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Financial Period"
        verbose_name_plural = "Financial Periods"
        ordering = ["entity", "-start_date"]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def as_of(self) -> date_type:
        """Reference date: end_date if closed, else today."""
        return self.end_date if self.end_date is not None else date_type.today()

    @property
    def is_closed(self) -> bool:
        return self.end_date is not None and self.end_date < date_type.today()

    @property
    def is_profit(self) -> bool:
        return self.amount is not None and self.amount > Decimal("0.00")

    @property
    def is_loss(self) -> bool:
        return self.amount is not None and self.amount < Decimal("0.00")

    @property
    def distributed(self) -> Decimal:
        """Sum of active (non-reversed) ProfitDistribution operations on this period."""
        from apps.app_operation.models.operation import Operation
        from apps.app_operation.models.operation_type import OperationType

        return Operation.objects.filter(
            plan=self,
            operation_type=OperationType.PROFIT_DISTRIBUTION,
            reversal_of__isnull=True,
            reversed_by__isnull=True,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    @property
    def covered(self) -> Decimal:
        """Sum of active (non-reversed) LossCoverage operations on this period."""
        from apps.app_operation.models.operation import Operation
        from apps.app_operation.models.operation_type import OperationType

        return Operation.objects.filter(
            plan=self,
            operation_type=OperationType.LOSS_COVERAGE,
            reversal_of__isnull=True,
            reversed_by__isnull=True,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    @property
    def remaining_distributable(self) -> Decimal:
        """How much profit is still available to distribute."""
        if not self.is_profit:
            return Decimal("0.00")
        return self.amount - self.distributed

    @property
    def remaining_coverable(self) -> Decimal:
        """How much loss is still available to be covered (positive number)."""
        if not self.is_loss:
            return Decimal("0.00")
        return abs(self.amount) - self.covered

    @property
    def allocations_balanced(self) -> bool:
        """True if shareholder allocations sum to ~100% (float tolerance)."""
        total = self.allocations.aggregate(total=Sum("percent"))["total"] or Decimal(
            "0.00"
        )
        return abs(total - Decimal("100.00")) <= Decimal("0.01")

    # ------------------------------------------------------------------
    # Balance-sheet snapshots (as of end_date)
    # ------------------------------------------------------------------

    def _incoming_tx_sum(self, types, date_lte=None) -> Decimal:
        """
        Sum incoming transactions of the given types into entity's fund.
        Reversed and reversal transactions are included so that cross-period
        reversals are counted in the period they actually occurred in.
        """
        from apps.app_transaction.models import Transaction

        filters: dict = dict(
            target=self.entity,
            type__in=types,
        )
        if date_lte is not None:
            filters["date__date__lte"] = date_lte
        return Transaction.objects.filter(**filters).aggregate(total=Sum("amount"))[
            "total"
        ] or Decimal("0.00")

    def _outgoing_tx_sum(self, types, date_lte=None) -> Decimal:
        """
        Sum outgoing transactions of the given types from entity's fund.
        Reversed and reversal transactions are included so that cross-period
        reversals are counted in the period they actually occurred in.
        """
        from apps.app_transaction.models import Transaction

        filters: dict = dict(
            source=self.entity,
            type__in=types,
        )
        if date_lte is not None:
            filters["date__date__lte"] = date_lte
        return Transaction.objects.filter(**filters).aggregate(total=Sum("amount"))[
            "total"
        ] or Decimal("0.00")

    @property
    def previous_balance(self) -> Decimal:
        """Entity fund balance as of start_date (beginning balance for this period)."""
        from datetime import timedelta

        day_before = self.start_date - timedelta(days=1)
        return self.entity.balance_at(day_before)

    @property
    def balance(self) -> Decimal:
        """Entity fund balance as of as_of (end_date if closed, else today)."""
        return self.entity.balance_at(self.as_of)

    @property
    def end_balance(self) -> Optional[Decimal]:
        """
        Entity fund balance as of end_date (cumulative, not period-only).
        Returns None when the period is still open (end_date is None).
        """
        if self.end_date is None:
            return None
        return self.entity.balance_at(self.end_date)

    @property
    def receivables(self) -> Decimal:
        """Outstanding receivables as of as_of."""
        return self.entity.receivables_at(self.as_of)

    @property
    def payables(self) -> Decimal:
        """Outstanding payables as of as_of."""
        return self.entity.payables_at(self.as_of)

    @property
    def cash_in(self) -> Decimal:
        """Total incoming cash payments as of as_of."""
        from apps.app_transaction.transaction_type import TransactionType

        return self._incoming_tx_sum(TransactionType.payment_types(), self.as_of)

    @property
    def cash_out(self) -> Decimal:
        """Total outgoing cash payments as of as_of."""
        from apps.app_transaction.transaction_type import TransactionType

        return self._outgoing_tx_sum(TransactionType.payment_types(), self.as_of)

    @property
    def payables_previous(self) -> Decimal:
        """Outstanding payables at start_date."""
        return self.entity.payables_at(self.start_date)

    @property
    def payables_in(self) -> Decimal:
        """New payables during the period."""
        return self.payables - self.payables_previous

    @property
    def payables_out(self) -> Decimal:
        """Payables paid during the period (negative of payables_in)."""
        return max(Decimal("0.00"), self.payables_previous - self.payables)

    @property
    def payables_end(self) -> Optional[Decimal]:
        """Outstanding payables at end_date (only if period is closed)."""
        if self.end_date is None:
            return None
        return self.entity.payables_at(self.end_date)

    @property
    def receivables_previous(self) -> Decimal:
        """Outstanding receivables at start_date."""
        return self.entity.receivables_at(self.start_date)

    @property
    def receivables_in(self) -> Decimal:
        """New receivables during the period."""
        return self.receivables - self.receivables_previous

    @property
    def receivables_out(self) -> Decimal:
        """Receivables collected during the period."""
        return max(Decimal("0.00"), self.receivables_previous - self.receivables)

    @property
    def receivables_end(self) -> Optional[Decimal]:
        """Outstanding receivables at end_date (only if period is closed)."""
        if self.end_date is None:
            return None
        return self.entity.receivables_at(self.end_date)

    @property
    def inventory_value_previous(self) -> Decimal:
        """Inventory value at start_date."""
        from apps.app_inventory.models import ProductLedgerEntry

        return ProductLedgerEntry.inventory_value_at(self.entity, self.start_date)

    @property
    def inventory_value_in(self) -> Decimal:
        """Inventory added during the period."""
        return self.inventory_value - self.inventory_value_previous

    @property
    def inventory_value_out(self) -> Decimal:
        """Inventory reduced/sold during the period."""
        return max(
            Decimal("0.00"), self.inventory_value_previous - self.inventory_value
        )

    @property
    def inventory_value_end(self) -> Optional[Decimal]:
        """Inventory value at end_date (only if period is closed)."""
        if self.end_date is None:
            return None
        from apps.app_inventory.models import ProductLedgerEntry

        return ProductLedgerEntry.inventory_value_at(self.entity, self.end_date)

    @property
    def inventory_value(self) -> Decimal:
        """Net book value of inventory as of as_of, derived from ProductLedgerEntry."""
        from apps.app_inventory.models import ProductLedgerEntry

        return ProductLedgerEntry.inventory_value_at(self.entity, self.as_of)

    @property
    def remaining_inventory_value(self) -> Decimal:
        """
        Net inventory value as of end_date:
            total purchase amounts (entity as buyer)
          - total sale amounts (entity as seller, at sale price)
        Uses operation base amounts; adjustments are not included.
        """
        from apps.app_operation.models.operation import Operation
        from apps.app_operation.models.operation_type import OperationType

        date_filter: dict = (
            {} if self.end_date is None else {"date__lte": self.end_date}
        )
        base = dict(reversal_of__isnull=True, reversed_by__isnull=True, **date_filter)

        purchases = Operation.objects.filter(
            source=self.entity,
            operation_type=OperationType.PURCHASE,
            **base,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        sales = Operation.objects.filter(
            destination=self.entity,
            operation_type=OperationType.SALE,
            **base,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        return purchases - sales

    @property
    def outstanding_loan_credited(self) -> Decimal:
        """
        Amount the entity is owed as creditor (lent out but not yet repaid):
            disbursed via LOAN_PAYMENT - recovered via LOAN_REPAYMENT, as of end_date.
        """
        from apps.app_transaction.transaction_type import TransactionType

        loaned = self._outgoing_tx_sum([TransactionType.LOAN_PAYMENT], self.end_date)
        repaid = self._incoming_tx_sum([TransactionType.LOAN_REPAYMENT], self.end_date)
        return loaned - repaid

    @property
    def outstanding_worker_advance_paid(self) -> Decimal:
        """
        Advance amounts the entity paid to workers not yet recovered:
            paid via WORKER_ADVANCE_PAYMENT - recovered via WORKER_ADVANCE_REPAYMENT, as of end_date.
        """
        from apps.app_transaction.transaction_type import TransactionType

        paid = self._outgoing_tx_sum(
            [TransactionType.WORKER_ADVANCE_PAYMENT], self.end_date
        )
        recovered = self._incoming_tx_sum(
            [TransactionType.WORKER_ADVANCE_REPAYMENT], self.end_date
        )
        return paid - recovered

    @property
    def end_assets(self) -> Optional[Decimal]:
        """
        Total assets at end_date:
            cash balance + remaining inventory + outstanding loan credits + outstanding worker advances paid.
        Returns None when the period is still open.
        """
        if self.end_date is None:
            return None
        from apps.app_transaction.transaction_type import TransactionType

        balance: Decimal = self._incoming_tx_sum(
            TransactionType.payment_types(), self.end_date
        ) - self._outgoing_tx_sum(TransactionType.payment_types(), self.end_date)
        return (
            balance
            + self.remaining_inventory_value
            + self.outstanding_loan_credited
            + self.outstanding_worker_advance_paid
        )

    @property
    def outstanding_loan_received(self) -> Decimal:
        """
        Amount the entity owes as debtor (received but not yet repaid):
            received via LOAN_PAYMENT - repaid via LOAN_REPAYMENT, as of end_date.
        """
        from apps.app_transaction.transaction_type import TransactionType

        received = self._incoming_tx_sum([TransactionType.LOAN_PAYMENT], self.end_date)
        repaid = self._outgoing_tx_sum([TransactionType.LOAN_REPAYMENT], self.end_date)
        return received - repaid

    @property
    def outstanding_worker_advance_received(self) -> Decimal:
        """
        Advance amounts received by the entity (as a worker) not yet repaid:
            received via WORKER_ADVANCE_PAYMENT - repaid via WORKER_ADVANCE_REPAYMENT, as of end_date.
        """
        from apps.app_transaction.transaction_type import TransactionType

        received = self._incoming_tx_sum(
            [TransactionType.WORKER_ADVANCE_PAYMENT], self.end_date
        )
        repaid = self._outgoing_tx_sum(
            [TransactionType.WORKER_ADVANCE_REPAYMENT], self.end_date
        )
        return received - repaid

    @property
    def end_liabilities(self) -> Decimal:
        """
        Total obligations against the entity at end_date:
            loans received but not yet repaid + worker advances received but not yet repaid.
        """
        return self.outstanding_loan_received + self.outstanding_worker_advance_received

    # ------------------------------------------------------------------
    # Business actions
    # ------------------------------------------------------------------

    def compute_profit_loss(self) -> "FinancialPeriod":
        """
        Derive amount from entity.profit_loss(self) and save.
        The period must be closed and the entity must be a project.
        """
        self.amount = self.entity.profit_loss(self)
        self.save()
        return self

    def close(self, end_date: Optional[date_type] = None) -> "FinancialPeriod | None":
        """
        Close this period by setting end_date.
        If the entity is still active, automatically opens the next period
        starting on end_date and returns it; otherwise returns None.
        end_date must be > start_date.
        """
        if self.end_date is not None:
            raise ValidationError("This period is already closed.")
        if end_date is None:
            end_date = date_type.today()

        if end_date < self.start_date:
            raise ValidationError(
                f"end_date must be strictly after start_date ({self.start_date})."
            )

        self.end_date = end_date
        self.save()
        if self.entity.active:
            next_period = FinancialPeriod(entity=self.entity, start_date=end_date)
            next_period.save()
            return next_period
        return None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean_end_date(self):
        if self.end_date and self.end_date <= self.start_date:
            raise ValidationError("end_date must be strictly greater than start_date.")

    def clean(self):
        if self.amount is not None and self.entity_id:
            if not self.entity.is_project:
                raise ValidationError(
                    "Only project entities can have a profit/loss amount."
                )
            if not self.is_closed:
                raise ValidationError(
                    "Cannot set profit/loss amount on an open period. Close the period first."
                )
        if self.entity_id and self.start_date:
            self._validate_no_overlap()
        return super().clean()

    def _validate_no_overlap(self):
        """Ensure no existing period for this entity overlaps with [start_date, end_date)."""
        qs = FinancialPeriod.objects.filter(entity=self.entity)
        if self.pk:
            qs = qs.exclude(pk=self.pk)

        # Half-open interval overlap: [A.start, A.end) overlaps [B.start, B.end)
        # iff A.start < B.end AND B.start < A.end  (strict inequalities).
        # For open-ended periods (end_date=None), treat end as +∞.
        if self.end_date:
            # Our interval: [start_date, end_date)
            # Overlap iff other.start_date < self.end_date AND (other.end_date is None OR other.end_date > self.start_date)
            qs = qs.filter(start_date__lt=self.end_date).filter(
                Q(end_date__isnull=True) | Q(end_date__gt=self.start_date)
            )
        else:
            # Our interval: [start_date, ∞)
            # Overlap iff (other.end_date is None OR other.end_date > self.start_date)
            qs = qs.filter(Q(end_date__isnull=True) | Q(end_date__gt=self.start_date))

        if qs.exists():
            raise ValidationError(
                "This period overlaps with an existing financial period for this entity."
            )

    def __str__(self):
        status = f"→ {self.end_date}" if self.end_date else "open"
        return f"Period [{self.start_date} {status}] for {self.entity}"
