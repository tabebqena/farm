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
    "Labor & Personnel": [
        {
            "name": "Permanent Staff Salaries",
            "type": "EXPENSE",
            "desc": "Labor & Personnel: Monthly wages",
        },
        {
            "name": "Casual/Daily Labor",
            "type": "EXPENSE",
            "desc": "Labor & Personnel: One-off help",
        },
        {
            "name": "Security Services",
            "type": "EXPENSE",
            "desc": "Labor & Personnel: Security fees",
        },
        {
            "name": "Staff Training & PPE",
            "type": "EXPENSE",
            "desc": "Labor & Personnel: Safety gear and training",
        },
        {
            "name": "Workers' Compensation",
            "type": "EXPENSE",
            "desc": "Labor & Personnel: Insurance for employees",
        },
    ],
    "Professional Services": [
        {
            "name": "Veterinary Consultation",
            "type": "EXPENSE",
            "desc": "Professional Services: Clinical fees",
        },
        {
            "name": "Breeding/AI Technical Fees",
            "type": "EXPENSE",
            "desc": "Professional Services: AI fees",
        },
        {
            "name": "Shearing/Hoof Trimming",
            "type": "EXPENSE",
            "desc": "Professional Services: Maintenance",
        },
        {
            "name": "Laboratory & Diagnostics",
            "type": "EXPENSE",
            "desc": "Professional Services: Testing and lab fees",
        },
        {
            "name": "Pedigree & Registration",
            "type": "EXPENSE",
            "desc": "Professional Services: Breed association fees",
        },
    ],
    "Infrastructure & Utilities": [
        {
            "name": "Electricity/Energy",
            "type": "EXPENSE",
            "desc": "Utilities: Power & Heating",
        },
        {
            "name": "Water Access Fees",
            "type": "EXPENSE",
            "desc": "Utilities: Pumping & Access",
        },
        {
            "name": "Machinery Servicing",
            "type": "EXPENSE",
            "desc": "Utilities: Repairs labor",
        },
        {
            "name": "Irrigation Maintenance",
            "type": "EXPENSE",
            "desc": "Utilities: Repairs to water systems",
        },
        {
            "name": "Waste & Manure Management",
            "type": "EXPENSE",
            "desc": "Environmental: Disposal and treatment",
        },
        {
            "name": "Internet & Communications",
            "type": "EXPENSE",
            "desc": "Utilities: Farm connectivity",
        },
    ],
    "Land & Logistics": [
        {
            "name": "Land Lease/Rent",
            "type": "EXPENSE",
            "desc": "Fixed: Grazing land lease",
        },
        {
            "name": "Pasture Maintenance",
            "type": "EXPENSE",
            "desc": "Land: Fertilizers, seeds, and weed control",
        },
        {
            "name": "Animal Transport",
            "type": "EXPENSE",
            "desc": "Logistics: Trucking services",
        },
        {
            "name": "Slaughter Fees",
            "type": "EXPENSE",
            "desc": "Logistics: Abattoir service fees",
        },
    ],
    "Maintenance & Fuel": [
        {
            "name": "Fuel (Diesel/Petrol)",
            "type": "EXPENSE",
            "desc": "Maintenance: Vehicle and generator fuel",
        },
        {
            "name": "Lubricants & Grease",
            "type": "EXPENSE",
            "desc": "Maintenance: Oil and machinery fluids",
        },
        {
            "name": "Fencing & Gate Repairs",
            "type": "EXPENSE",
            "desc": "Maintenance: Boundary and paddock upkeep",
        },
        {
            "name": "Building & Shed Repairs",
            "type": "EXPENSE",
            "desc": "Maintenance: Structures and roofing",
        },
        {
            "name": "Small Tools & Supplies",
            "type": "EXPENSE",
            "desc": "Maintenance: Workshop consumables",
        },
    ],
    "Marketing & Sales": [
        {
            "name": "Marketing & Advertising",
            "type": "EXPENSE",
            "desc": "Sales: Promoting products/livestock",
        },
        {
            "name": "Sales Commissions",
            "type": "EXPENSE",
            "desc": "Sales: Broker or auctioneer fees",
        },
        {
            "name": "Packaging & Branding",
            "type": "EXPENSE",
            "desc": "Sales: Labels and design",
        },
    ],
    "Administrative & Finance": [
        {
            "name": "Insurance Premiums",
            "type": "EXPENSE",
            "desc": "Admin: Livestock and property coverage",
        },
        {
            "name": "Accounting & Legal",
            "type": "EXPENSE",
            "desc": "Admin: Professional consultancy",
        },
        {
            "name": "Licenses & Permits",
            "type": "EXPENSE",
            "desc": "Admin: Regulatory compliance fees",
        },
        {
            "name": "Bank Fees & Interest",
            "type": "EXPENSE",
            "desc": "Admin: Transaction and loan costs",
        },
        {
            "name": "Stationery & Office",
            "type": "EXPENSE",
            "desc": "Admin: Printing and office supplies",
        },
    ],
}


def get_flat_default_categories():
    """Helper to return default_categories as a flat name-to-details dictionary."""
    flat = {}
    for aspect, items in default_categories.items():
        for item in items:
            flat[item["name"]] = {"type": item["type"], "desc": item["desc"]}
    return flat


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
