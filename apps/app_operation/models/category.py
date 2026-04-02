import logging
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.app_base.models import BaseModel

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Default Categories
# ─────────────────────────────────────────────────────────────────────────────

default_categories = {
    # Labor
    "Permanent Staff Salaries": {
        "type": "EXPENSE",
        "desc": "Labor & Personnel: Monthly wages",
    },
    "Casual/Daily Labor": {
        "type": "EXPENSE",
        "desc": "Labor & Personnel: One-off help",
    },
    "Security Services": {
        "type": "EXPENSE",
        "desc": "Labor & Personnel: Security fees",
    },
    # Professional
    "Veterinary Consultation": {
        "type": "EXPENSE",
        "desc": "Professional Services: Clinical fees",
    },
    "Breeding/AI Technical Fees": {
        "type": "EXPENSE",
        "desc": "Professional Services: AI fees",
    },
    "Shearing/Hoof Trimming": {
        "type": "EXPENSE",
        "desc": "Professional Services: Maintenance",
    },
    # Infrastructure
    "Electricity/Energy": {"type": "EXPENSE", "desc": "Utilities: Power & Heating"},
    "Water Access Fees": {"type": "EXPENSE", "desc": "Utilities: Pumping & Access"},
    "Machinery Servicing": {"type": "EXPENSE", "desc": "Utilities: Repairs labor"},
    # Purchases (Inventory)
    "Animal Feed Stock": {
        "type": "PURCHASE",
        "desc": "Inventory: Bulk feed & supplements",
    },
    "Medical Supplies": {"type": "PURCHASE", "desc": "Inventory: Vaccines & meds"},
    # Sales (Revenue)
    "Livestock Sales": {"type": "SALE", "desc": "Revenue: Sale of live animals"},
    "Milk/Dairy Sales": {"type": "SALE", "desc": "Revenue: Sale of dairy products"},
    # Land & Logistics
    "Land Lease/Rent": {"type": "EXPENSE", "desc": "Fixed: Grazing land lease"},
    "Animal Transport": {"type": "EXPENSE", "desc": "Logistics: Trucking services"},
    "Slaughter Fees": {"type": "EXPENSE", "desc": "Logistics: Abattoir service fees"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Financial Category
# ─────────────────────────────────────────────────────────────────────────────


class FinancialCategory(BaseModel):
    TYPE_CHOICES = [
        ("PURCHASE", "Purchase"),
        ("SALE", "Sale"),
        ("EXPENSE", "Expense"),
    ]

    name = models.CharField(max_length=100)
    parent_entity = models.ForeignKey(
        "app_entity.Entity", on_delete=models.CASCADE, related_name="categories"
    )
    category_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default="EXPENSE"
    )
    max_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("name", "parent_entity")
        verbose_name_plural = "Financial Categories"

    def __str__(self):
        return f"{self.name} ({self.category_type})"
