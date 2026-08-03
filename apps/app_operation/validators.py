"""
Validators and data parsers for operation creation flows.

Provides ``OperationDataValidator`` — a standalone validator that extracts and
validates POST data into a clean ``ParsedOperationData`` dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date

if TYPE_CHECKING:
    from django.http import QueryDict


# ---------------------------------------------------------------------------
# Data contract
# ---------------------------------------------------------------------------


@dataclass
class ParsedOperationData:
    """Clean, validated data extracted from the creation form POST."""

    date: date
    description: str
    selected_category_id: int | None = None
    amount_paid: Decimal = Decimal("0.00")
    raw_post: QueryDict | None = None  # forwarded for internal formset rebinding
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class OperationDataValidator:
    """
    Validates and parses raw POST data for operation creation.

    Usage::

        validator = OperationDataValidator(request.POST, view_config)
        try:
            parsed = validator.validate()
        except ValidationError as e:
            # handle errors
    """

    def __init__(self, post_data: QueryDict, view_config: dict) -> None:
        self._post = post_data
        self._cfg = view_config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self) -> ParsedOperationData:
        """
        Parse and validate POST data.

        Returns a ``ParsedOperationData`` instance on success.

        Raises ``ValidationError`` if required fields are missing or invalid.
        """
        errors: list[str] = []

        date_val = self._parse_date(errors)
        description = self._post.get("description", "")
        category_id = self._parse_category(errors)
        amount_paid = self._parse_amount_paid(errors)

        if errors:
            raise ValidationError("; ".join(errors))

        return ParsedOperationData(
            date=date_val,
            description=description,
            selected_category_id=category_id,
            amount_paid=amount_paid,
            raw_post=self._post,
        )

    # ------------------------------------------------------------------
    # Field-level parsers
    # ------------------------------------------------------------------

    def _parse_date(self, errors: list[str]) -> date:
        date_str = self._post.get("date", "")
        if date_str:
            parsed = parse_date(date_str)
            if parsed is None:
                errors.append("Invalid date format.")
                return timezone.now().date()
            return parsed
        return timezone.now().date()

    def _parse_category(self, errors: list[str]) -> int | None:
        cat_raw = self._post.get("category", "")
        if not cat_raw:
            if self._cfg.get("category_required"):
                errors.append("Category is required for this operation.")
            return None
        try:
            return int(cat_raw)
        except (ValueError, TypeError):
            errors.append("Invalid category selection.")
            return None

    def _parse_amount_paid(self, errors: list[str]) -> Decimal:
        raw = self._post.get("amount_paid", "")
        if not raw:
            return Decimal("0.00")
        try:
            val = Decimal(raw)
            if val < Decimal("0.00"):
                errors.append("Amount paid cannot be negative.")
                return Decimal("0.00")
            return val
        except Exception:
            errors.append("Invalid amount paid value.")
            return Decimal("0.00")
