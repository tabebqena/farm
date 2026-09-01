"""Shared ORM setup helpers for the inventory / category UI happy-path tests.

These mirror the fixture patterns used by the existing inventory tests so the
browser sees the exact world the model suites assert on.
"""
from datetime import date
from decimal import Decimal

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InventoryMovementLine,
    InvoiceItem,
    Product,
    ProductTemplate,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation


def make_category(project, name="Salaries", category_type="EXPENSE"):
    """An active financial category linked to ``project``."""
    from apps.app_entity.models.category import (
        FinancialCategoriesEntitiesRelations,
        FinancialCategory,
    )

    cat = FinancialCategory.objects.create(name=name, aspect=name, category_type=category_type)
    FinancialCategoriesEntitiesRelations.objects.create(
        entity=project, category=cat, is_active=True
    )
    return cat


def make_product_template(
    project,
    name="Feed Mix",
    nature=ProductTemplate.Nature.FEED,
    default_unit="Kg",
    minimum_quantity=Decimal("1.00"),
    **kwargs,
):
    """A product template assigned to ``project``.

    ``tracking_mode`` defaults from the nature (ANIMAL → INDIVIDUAL, otherwise
    COMMODITY), mirroring what ``ProductTemplate.clean()`` would derive —
    ``objects.create`` bypasses ``clean()``, so the caller must set it.
    """
    if "tracking_mode" not in kwargs:
        kwargs["tracking_mode"] = ProductTemplate.tracking_mode_for_nature(nature)
    template = ProductTemplate.objects.create(
        name=name,
        nature=nature,
        sub_category=kwargs.pop("sub_category", "Feed"),
        default_unit=default_unit,
        minimum_quantity=minimum_quantity,
        **kwargs,
    )
    template.entities.add(project)
    return template


def make_vendor(project, name="Vendor"):
    """A vendor PERSON stakeholder of ``project``."""
    vendor = Entity.create(EntityType.PERSON, name=name, is_vendor=True)
    Stakeholder.objects.create(
        parent=project, target=vendor, active=True, role=StakeholderRole.VENDOR
    )
    return vendor


def make_client(project, name="Client"):
    """A client PERSON stakeholder of ``project``."""
    client = Entity.create(EntityType.PERSON, name=name, is_client=True)
    Stakeholder.objects.create(
        parent=project, target=client, active=True, role=StakeholderRole.CLIENT
    )
    return client


def make_moved_product(project, template, qty, price, officer, vendor=None):
    """Return an ACTIVE, physically-present product owned by ``project``.

    Mirrors test_quick_consume_from_stock._make_moved_product: a PURCHASE op
    (via objects.create to bypass clean) + invoice item + product + inbound
    movement line.
    """
    vendor = vendor or make_vendor(project, name="Movement Vendor")
    purchase = PurchaseOperation.objects.create(
        source=project,
        destination=vendor,
        officer=officer,
        operation_type=OperationType.PURCHASE,
        amount=(qty * price).quantize(Decimal("0.01")),
    )
    item = InvoiceItem.objects.create(
        operation=purchase, product_template=template, quantity=qty, unit_price=price
    )
    product = Product.objects.create(
        product_template=template,
        entity=project,
        unit_price=price,
        quantity=int(qty),
    )
    product.invoice_items.add(item)
    InventoryMovementLine.objects.create(
        operation=purchase,
        invoice_item=item,
        product=product,
        quantity=qty,
        date=date.today(),
        officer=officer,
    )
    return product
