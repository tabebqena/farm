from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from apps.app_base.models import BaseModel


class ShareholderAllocation(BaseModel):
    """
    Instructional (advisory) percentage for a shareholder within a FinancialPeriod.
    Does not enforce how much the user actually distributes/covers.
    """

    period = models.ForeignKey(
        "app_operation.FinancialPeriod",
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
                fields=["period", "shareholder"],
                name="unique_allocation_per_period_shareholder",
            )
        ]

    @property
    def instructional_amount(self) -> Decimal:
        return (self.period.amount * self.percent / Decimal("100")).quantize(
            Decimal("0.01")
        )

    def clean(self):
        if self.shareholder_id and not self.shareholder.is_shareholder:
            raise ValidationError("Allocation target must be a shareholder entity.")
        if self.percent is not None and self.percent < 0:
            raise ValidationError("Percent cannot be negative.")
        return super().clean()

    def __str__(self):
        return f"{self.shareholder} — {self.percent}% of {self.period}"
