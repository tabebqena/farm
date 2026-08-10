"""
Tests for InvoiceItemAdjustment and InvoiceItemAdjustmentLine.

Concern breakdown:
  - InvoiceItemAdjustment  → item-level changes + ProductLedgerEntry sync
  - Adjustment             → financial transactions (created by finalize())
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_adjustment.models import (
    InvoiceItemAdjustment,
    InvoiceItemAdjustmentLine,
    InvoiceItemAdjustmentType,
)
from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InvoiceItem,
    Product,
    ProductTemplate,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation, SaleOperation

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username="officer"):
    return User.objects.create_user(username=username, password="x", is_staff=True)


def _make_project(name="Farm"):
    return Entity.create(EntityType.PROJECT, name=name)


def _make_vendor(name="Vendor"):
    return Entity.create(EntityType.PERSON, name=name, is_vendor=True)


def _make_client(name="Client"):
    return Entity.create(EntityType.PROJECT, name=name, is_client=True)


def _link_vendor(project_entity, vendor_entity):
    sh = Stakeholder(
        parent=project_entity,
        target=vendor_entity,
        role=StakeholderRole.VENDOR,
        active=True,
    )
    sh.save()


def _link_client(project_entity, client_entity):
    sh = Stakeholder(
        parent=project_entity,
        target=client_entity,
        role=StakeholderRole.CLIENT,
        active=True,
    )
    sh.save()


def _make_purchase_op(
    project_entity, vendor_entity, officer, amount=Decimal("1000.00")
):
    op = PurchaseOperation.objects.create(
        source=project_entity,
        destination=vendor_entity,
        amount=amount,
        operation_type=OperationType.PURCHASE,
        date=date.today(),
        officer=officer,
    )
    return op


def _make_sale_op(client_entity, project_entity, officer, amount=Decimal("1000.00")):
    op = SaleOperation.objects.create(
        source=client_entity,
        destination=project_entity,
        amount=amount,
        operation_type=OperationType.SALE,
        date=date.today(),
        officer=officer,
    )
    return op


def _make_product_template(name="Cattle"):
    return ProductTemplate.objects.create(
        name=name,
        nature=ProductTemplate.Nature.ANIMAL,
        tracking_mode=ProductTemplate.TrackingMode.BATCH,
        default_unit="Head",
    )


def _make_invoice_with_item(operation, template, quantity, unit_price):
    item = InvoiceItem.objects.create(
        operation=operation,
        product_template=template,
        quantity=quantity,
        unit_price=unit_price,
    )
    return item


def _make_product_for_item(template, item, unit_price, quantity=1):
    product = Product.objects.create(
        product_template=template, unit_price=unit_price, quantity=quantity
    )
    product.invoice_items.add(item)
    return product


def _make_item_adj(operation, adj_type, officer, reason=""):
    ia = InvoiceItemAdjustment(
        operation=operation,
        type=adj_type,
        date=date.today(),
        officer=officer,
        reason=reason,
    )
    ia.full_clean()
    ia.save()
    return ia


def _make_line(item_adj, invoice_item, **kwargs):
    line = InvoiceItemAdjustmentLine(
        adjustment=item_adj, invoice_item=invoice_item, **kwargs
    )
    line.full_clean()
    line.save()
    return line


# ---------------------------------------------------------------------------
# FinalizationTest
# ---------------------------------------------------------------------------


class ValidationTest(TestCase):
    """Model-level validation rules."""

    def setUp(self):
        self.officer = _make_officer()
        self.project = _make_project()
        self.vendor = _make_vendor()
        _link_vendor(self.project, self.vendor)
        self.template = _make_product_template()

    def test_item_adjustment_requires_purchase_or_sale(self):
        from apps.app_entity.models.category import FinancialCategory
        from apps.app_operation.models.proxies import ExpenseOperation

        world = Entity.create(EntityType.WORLD)
        cat, _ = FinancialCategory.objects.get_or_create(
            name="Veterinary Consultation",
            aspect="Medications",
            defaults={"category_type": "EXPENSE"},
        )
        op = ExpenseOperation.objects.create(
            source=self.project,
            destination=world,
            amount=Decimal("500.00"),
            operation_type=OperationType.EXPENSE,
            date=date.today(),
            officer=self.officer,
            category=cat,
        )
        ia = InvoiceItemAdjustment(
            operation=op,
            type=InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE,
            date=date.today(),
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            ia.full_clean()

    def test_type_must_match_operation(self):
        op = _make_purchase_op(self.project, self.vendor, self.officer)
        ia = InvoiceItemAdjustment(
            operation=op,
            type=InvoiceItemAdjustmentType.SALE_ITEM_DECREASE,  # wrong for PURCHASE
            date=date.today(),
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            ia.full_clean()

    def test_line_requires_at_least_one_change_field(self):
        op = _make_purchase_op(self.project, self.vendor, self.officer)
        item = _make_invoice_with_item(
            op, self.template, Decimal("5"), Decimal("100.00")
        )
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        line = InvoiceItemAdjustmentLine(
            adjustment=ia,
            invoice_item=item,
            # nothing set — new_quantity=None, new_unit_price=None
        )
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_line_must_belong_to_same_operation(self):
        op1 = _make_purchase_op(self.project, self.vendor, self.officer)
        op2 = _make_purchase_op(
            self.project, self.vendor, self.officer, Decimal("500.00")
        )
        item_of_op2 = _make_invoice_with_item(
            op2, self.template, Decimal("5"), Decimal("100.00")
        )
        ia = _make_item_adj(
            op1, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        line = InvoiceItemAdjustmentLine(
            adjustment=ia, invoice_item=item_of_op2, new_unit_price=Decimal("80.00")
        )
        with self.assertRaises(ValidationError):
            line.full_clean()


# ---------------------------------------------------------------------------
# DecreaseWithMovementsTest
# ---------------------------------------------------------------------------


class DecreaseWithMovementsTest(TestCase):
    """Decreasing quantity when products have inventory movements."""

    def setUp(self):
        self.officer = _make_officer()
        self.project = _make_project()
        self.vendor = _make_vendor()
        _link_vendor(self.project, self.vendor)
        self.template = _make_product_template()
        self.op = _make_purchase_op(
            self.project, self.vendor, self.officer, Decimal("1000.00")
        )
        self.item = _make_invoice_with_item(
            self.op, self.template, Decimal("10"), Decimal("100.00")
        )
        self.product = _make_product_for_item(
            self.template, self.item, Decimal("100.00"), quantity=10
        )

    def _simulate_movement(self):
        """Create a movement line so the product is considered 'moved'."""
        from apps.app_inventory.models import InventoryMovementLine

        InventoryMovementLine.objects.create(
            operation=self.op,
            invoice_item=self.item,
            product=self.product,
            quantity=Decimal("5.00"),
            date=date.today(),
            officer=self.officer,
        )

    def test_decrease_quantity_with_moved_products_succeeds(self):
        """Decreasing qty on an item whose products have movements must NOT raise."""
        self._simulate_movement()
        ia = _make_item_adj(
            self.op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        # This would have raised ValidationError before _sync_products() was removed
        line = InvoiceItemAdjustmentLine(
            adjustment=ia,
            invoice_item=self.item,
            new_quantity=Decimal("8.00"),
        )
        line.full_clean()
        line.save()  # must not raise

    def test_decrease_price_with_moved_products_succeeds(self):
        """Decreasing unit price on an item with moved products must NOT raise."""
        self._simulate_movement()
        ia = _make_item_adj(
            self.op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        line = InvoiceItemAdjustmentLine(
            adjustment=ia,
            invoice_item=self.item,
            new_unit_price=Decimal("80.00"),
        )
        line.full_clean()
        line.save()  # must not raise

    def test_increase_with_moved_products_succeeds(self):
        """Increasing qty/price on an item with moved products must NOT raise."""
        self._simulate_movement()
        ia = _make_item_adj(
            self.op, InvoiceItemAdjustmentType.PURCHASE_ITEM_INCREASE, self.officer
        )
        line = InvoiceItemAdjustmentLine(
            adjustment=ia,
            invoice_item=self.item,
            new_quantity=Decimal("12.00"),
            new_unit_price=Decimal("110.00"),
        )
        line.full_clean()
        line.save()  # must not raise

    def test_ledger_entry_still_recorded_after_movement(self):
        """ProductLedgerEntry must still be recorded when products have movements."""
        self._simulate_movement()
        ia = _make_item_adj(
            self.op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        line = _make_line(ia, self.item, new_quantity=Decimal("8.00"))

        from apps.app_inventory.models import ProductLedgerEntry

        # record_adjustment_line() writes product=None — query by invoice item.
        entry = ProductLedgerEntry.objects.filter(
            invoice_item=self.item,
            entry_type=ProductLedgerEntry.EntryType.PURCHASE_ADJUSTMENT_DECREASE,
        ).latest("id")
        self.assertEqual(entry.quantity_delta, Decimal("-2.00"))
        self.assertEqual(entry.value_delta, Decimal("-200.00"))


# ---------------------------------------------------------------------------
# ImmutabilityTest
# ---------------------------------------------------------------------------
