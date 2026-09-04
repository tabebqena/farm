"""Financial-category models.

Defines :class:`FinancialCategory` (a named, typed category such as EXPENSE)
and :class:`FinancialCategoriesEntitiesRelations`, the through model linking
categories to entities with an optional spending ``max_limit``.
"""

import logging
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.app_base.models import BaseModel

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Financial Category
# ─────────────────────────────────────────────────────────────────────────────


class FinancialCategory(BaseModel):
    """A named, typed spending category (e.g. an EXPENSE aspect).

    Categories are linked to entities through
    :class:`FinancialCategoriesEntitiesRelations`, which can cap the category
    per entity via ``max_limit``.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    category_type = models.CharField(max_length=10, default="EXPENSE", editable=False)
    aspect = models.CharField(max_length=100)
    entity = models.ManyToManyField(
        "Entity",
        through="FinancialCategoriesEntitiesRelations",
        related_name="categories",
    )

    class Meta:
        verbose_name_plural = "Financial Categories"
        # Uniqueness is scoped to live rows only, so a soft-deleted category no
        # longer keeps its name "taken" forever (the old ``unique=True`` applied
        # to every row, tombstones included).
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_financial_category_name_live",
            )
        ]

    def __str__(self):
        return f"{self.name}"


class FinancialCategoriesEntitiesRelations(BaseModel):
    """Through model linking a :class:`FinancialCategory` to an :class:`Entity`.

    Carries an optional ``max_limit`` on the category for that entity and an
    ``is_active`` flag; relations are deactivated rather than hard-deleted.
    """

    entity = models.ForeignKey(
        "Entity",
        on_delete=models.CASCADE,
        related_name="financial_categories_entities_relations",
    )
    category = models.ForeignKey(
        FinancialCategory, on_delete=models.CASCADE, related_name="entities_relations"
    )
    max_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Financial Categories Entities Relations"
        # Scoped to live rows: soft-deleting a relation frees the (entity,
        # category) pair so it can be re-linked later. The old
        # ``unique_together`` applied to tombstones as well.
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "category"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_entity_category_relation_live",
            )
        ]

    def __str__(self):
        return f"{self.entity} - {self.category}"
