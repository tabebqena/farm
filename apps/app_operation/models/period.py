from datetime import date as date_type, timedelta
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

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
    """

    _immutable_fields = {
        "entity": {},
        "start_date": {},
        "end_date": {"ALLOW_SET": True, "NULL_VALUES": (None,)},
    }

    entity = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="financial_periods",
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Financial Period"
        verbose_name_plural = "Financial Periods"
        ordering = ["entity", "-start_date"]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_closed(self) -> bool:
        return self.end_date is not None and self.end_date < date_type.today()

    # ------------------------------------------------------------------
    # Business actions
    # ------------------------------------------------------------------

    def close(
        self, end_date: Optional[date_type] = None, auto_create_next=True
    ) -> "FinancialPeriod | None":
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
        if self.entity.active and auto_create_next:
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
