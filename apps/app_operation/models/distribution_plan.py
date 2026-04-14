from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum

from apps.app_base.mixins import ImmutableMixin
from apps.app_base.models import BaseModel


class DistributionPlan(ImmutableMixin, BaseModel):
    """
    Snapshot of a project's P&L for a closed financial period.
    Created manually after closing the period. Serves as the budget cap
    for ProfitDistributionOperation (amount > 0) and LossCoverageOperation
    (amount < 0) created against this project+period.

    amount > 0  → profit  → ProfitDistribution operations are allowed
    amount < 0  → loss    → LossCoverage operations are allowed
    amount == 0 → no operations can be created against this plan
    """

    _immutable_fields = {"entity": {}, "period": {}, "amount": {}}

    entity = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="distribution_plans",
    )
    period = models.ForeignKey(
        "app_operation.FinancialPeriod",
        on_delete=models.PROTECT,
        related_name="distribution_plans",
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)

    class Meta:
        verbose_name = "Distribution Plan"
        verbose_name_plural = "Distribution Plans"
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "period"],
                name="unique_distribution_plan_per_entity_period",
            )
        ]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_profit(self) -> bool:
        return self.amount > Decimal("0.00")

    @property
    def is_loss(self) -> bool:
        return self.amount < Decimal("0.00")

    @property
    def distributed(self) -> Decimal:
        """Sum of active (non-reversed) ProfitDistribution operations on this plan."""
        from apps.app_operation.models.operation import Operation
        from apps.app_operation.models.operation_type import OperationType

        return (
            Operation.objects.filter(
                plan=self,
                operation_type=OperationType.PROFIT_DISTRIBUTION,
                reversal_of__isnull=True,
                reversed_by__isnull=True,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

    @property
    def covered(self) -> Decimal:
        """Sum of active (non-reversed) LossCoverage operations on this plan."""
        from apps.app_operation.models.operation import Operation
        from apps.app_operation.models.operation_type import OperationType

        return (
            Operation.objects.filter(
                plan=self,
                operation_type=OperationType.LOSS_COVERAGE,
                reversal_of__isnull=True,
                reversed_by__isnull=True,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

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
        total = self.allocations.aggregate(total=Sum("percent"))["total"] or Decimal("0.00")
        return abs(total - Decimal("100.00")) <= Decimal("0.01")

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def calculate_amount(cls, entity, period) -> Decimal:
        """
        Period-scoped P&L calculation.
        Includes reversed and reversal operations (each period stands alone).
        Excludes soft-deleted operations.
        """
        from apps.app_operation.models.operation import Operation
        from apps.app_operation.models.operation_type import OperationType

        INCOME_TYPES = [
            OperationType.SALE,
            OperationType.CAPITAL_GAIN,
            OperationType.CORRECTION_CREDIT,
        ]
        COST_TYPES = [
            OperationType.EXPENSE,
            OperationType.PURCHASE,
            OperationType.CAPITAL_LOSS,
            OperationType.CORRECTION_DEBIT,
        ]

        base_qs = Operation.objects.filter(period=period)

        income = (
            base_qs.filter(
                Q(destination=entity, operation_type__in=INCOME_TYPES)
                | Q(destination=entity, operation_type=OperationType.PURCHASE)
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        costs = (
            base_qs.filter(
                Q(source=entity, operation_type__in=COST_TYPES)
                | Q(source=entity, operation_type=OperationType.SALE)
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        return income - costs

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        if self.entity_id and not self.entity.project:
            raise ValidationError("Distribution plan entity must be a project.")
        if self.period_id and self.entity_id:
            if self.period.entity_id != self.entity_id:
                raise ValidationError(
                    "The period does not belong to this project entity."
                )
            if not self.period.is_closed:
                raise ValidationError(
                    "Cannot create a distribution plan for an open period. Close the period first."
                )
        return super().clean()

    def __str__(self):
        sign = "Profit" if self.is_profit else ("Loss" if self.is_loss else "Break-even")
        return f"DistributionPlan [{sign} {self.amount}] — {self.entity} / {self.period}"


class ShareholderAllocation(BaseModel):
    """
    Instructional (advisory) percentage for a shareholder within a DistributionPlan.
    Does not enforce how much the user actually distributes/covers.
    """

    plan = models.ForeignKey(
        DistributionPlan,
        on_delete=models.CASCADE,
        related_name="allocations",
    )
    shareholder = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="shareholder_allocations",
    )
    percent = models.DecimalField(max_digits=6, decimal_places=3)

    class Meta:
        verbose_name = "Shareholder Allocation"
        verbose_name_plural = "Shareholder Allocations"
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "shareholder"],
                name="unique_allocation_per_plan_shareholder",
            )
        ]

    @property
    def instructional_amount(self) -> Decimal:
        return (self.plan.amount * self.percent / Decimal("100")).quantize(Decimal("0.01"))

    def clean(self):
        if self.shareholder_id and not self.shareholder.is_shareholder:
            raise ValidationError("Allocation target must be a shareholder entity.")
        if self.percent is not None and self.percent < 0:
            raise ValidationError("Percent cannot be negative.")
        return super().clean()

    def __str__(self):
        return f"{self.shareholder} — {self.percent}% of {self.plan}"
