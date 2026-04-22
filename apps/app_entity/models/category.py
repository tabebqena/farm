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

    name = models.CharField(max_length=100, unique=True)
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

    def __str__(self):
        return f"{self.name}"


class FinancialCategoriesEntitiesRelations(BaseModel):
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
        unique_together = ("entity", "category")
        verbose_name_plural = "Financial Categories Entities Relations"

    def __str__(self):
        return f"{self.entity} - {self.category}"
