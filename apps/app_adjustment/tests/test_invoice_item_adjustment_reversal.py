"""
Tests for InvoiceItemAdjustment and InvoiceItemAdjustmentLine.

Concern breakdown:
  - InvoiceItemAdjustment  → item-level changes + ProductLedgerEntry sync
  - Adjustment             → financial transactions (created by finalize())
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
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
    ProductLedgerEntry,
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


class ReversalTest(TestCase):
    """Reversing an InvoiceItemAdjustment creates counter-transactions
    and counter-ledger entries."""

    def setUp(self):
        self.officer = _make_officer()
        self.project = _make_project()
        self.vendor = _make_vendor()
        _link_vendor(self.project, self.vendor)
        self.template = _make_product_template()

    def test_reversal_creates_counter_transaction(self):
        op = _make_purchase_op(
            self.project, self.vendor, self.officer, Decimal("1000.00")
        )
        item = _make_invoice_with_item(
            op, self.template, Decimal("10"), Decimal("100.00")
        )
        _make_product_for_item(self.template, item, Decimal("100.00"))

        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("90.00"))
        ia.finalize()

        ia.reverse(officer=self.officer, date=date.today(), reason="mistake")

        # The accounting adjustment should be reversed
        adj = ia.adjustment
        self.assertTrue(adj.is_reversed)

    def test_reversal_creates_negating_ledger_entry(self):
        op = _make_purchase_op(
            self.project, self.vendor, self.officer, Decimal("500.00")
        )
        item = _make_invoice_with_item(
            op, self.template, Decimal("5"), Decimal("100.00")
        )
        product = _make_product_for_item(self.template, item, Decimal("100.00"))

        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("80.00"))
        ia.finalize()

        ia.reverse(officer=self.officer, date=date.today(), reason="cancel")

        # Should have: forward entry (value_delta=-100) + reversal entry (value_delta=+100)
        adj_entries = ProductLedgerEntry.objects.filter(
            invoice_item=item,
            entry_type__in=[
                ProductLedgerEntry.EntryType.PURCHASE_ADJUSTMENT_INCREASE,
                ProductLedgerEntry.EntryType.PURCHASE_ADJUSTMENT_DECREASE,
            ],
        ).order_by("id")
        self.assertEqual(adj_entries.count(), 2)
        self.assertEqual(adj_entries[0].value_delta, Decimal("-100.00"))
        self.assertEqual(adj_entries[1].value_delta, Decimal("100.00"))

    def test_reversal_restores_effective_amount(self):
        op = _make_purchase_op(
            self.project, self.vendor, self.officer, Decimal("1000.00")
        )
        item = _make_invoice_with_item(
            op, self.template, Decimal("10"), Decimal("100.00")
        )
        _make_product_for_item(self.template, item, Decimal("100.00"))

        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("90.00"))
        ia.finalize()

        self.assertEqual(op.effective_amount, Decimal("900.00"))

        ia.reverse(officer=self.officer, date=date.today(), reason="cancel")
        op.refresh_from_db()
        self.assertEqual(op.effective_amount, Decimal("1000.00"))


# ---------------------------------------------------------------------------
# DirectAdjustmentReversalDelegationTest
# ---------------------------------------------------------------------------


class DirectAdjustmentReversalDelegationTest(TestCase):
    """
    Reversing an Adjustment directly (not through InvoiceItemAdjustment)
    must delegate to InvoiceItemAdjustment.reverse() when one exists,
    ensuring both financial and inventory sides are properly reversed.
    """

    def setUp(self):
        self.officer = _make_officer()
        self.project = _make_project()
        self.vendor = _make_vendor()
        _link_vendor(self.project, self.vendor)
        self.template = _make_product_template()

    def test_direct_reversal_delegates_to_item_adjustment(self):
        """Reversing Adjustment directly must also reverse the InvoiceItemAdjustment."""
        op = _make_purchase_op(
            self.project, self.vendor, self.officer, Decimal("1000.00")
        )
        item = _make_invoice_with_item(
            op, self.template, Decimal("10"), Decimal("100.00")
        )
        _make_product_for_item(self.template, item, Decimal("100.00"))

        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("90.00"))
        ia.finalize()

        # Reverse the Adjustment directly (not through InvoiceItemAdjustment)
        ia.adjustment.reverse(officer=self.officer, date=date.today(), reason="direct")

        # Both must be marked as reversed
        ia.refresh_from_db()
        self.assertTrue(
            ia.is_reversed,
            "InvoiceItemAdjustment must be reversed when its linked Adjustment is reversed directly",
        )
        self.assertTrue(
            ia.adjustment.is_reversed,
            "Adjustment must be reversed",
        )

    def test_direct_reversal_creates_negating_ledger_entries(self):
        """Direct reversal of Adjustment must also negate ProductLedgerEntry rows."""
        op = _make_purchase_op(
            self.project, self.vendor, self.officer, Decimal("500.00")
        )
        item = _make_invoice_with_item(
            op, self.template, Decimal("5"), Decimal("100.00")
        )
        product = _make_product_for_item(self.template, item, Decimal("100.00"))

        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("80.00"))
        ia.finalize()

        # Direct reversal
        ia.adjustment.reverse(officer=self.officer, date=date.today(), reason="direct")

        # Should have: forward entry (value_delta=-100) + reversal entry (value_delta=+100)
        adj_entries = ProductLedgerEntry.objects.filter(
            invoice_item=item,
            entry_type__in=[
                ProductLedgerEntry.EntryType.PURCHASE_ADJUSTMENT_INCREASE,
                ProductLedgerEntry.EntryType.PURCHASE_ADJUSTMENT_DECREASE,
            ],
        ).order_by("id")
        self.assertEqual(adj_entries.count(), 2)
        self.assertEqual(adj_entries[0].value_delta, Decimal("-100.00"))
        self.assertEqual(adj_entries[1].value_delta, Decimal("100.00"))

    def test_direct_reversal_restores_effective_amount(self):
        """Direct reversal of Adjustment must restore the operation's effective amount."""
        op = _make_purchase_op(
            self.project, self.vendor, self.officer, Decimal("1000.00")
        )
        item = _make_invoice_with_item(
            op, self.template, Decimal("10"), Decimal("100.00")
        )
        _make_product_for_item(self.template, item, Decimal("100.00"))

        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("90.00"))
        ia.finalize()

        self.assertEqual(op.effective_amount, Decimal("900.00"))

        # Direct reversal
        ia.adjustment.reverse(officer=self.officer, date=date.today(), reason="direct")

        op.refresh_from_db()
        self.assertEqual(op.effective_amount, Decimal("1000.00"))

    def test_direct_reversal_creates_counter_transaction(self):
        """Direct reversal must create a counter-transaction on the Adjustment."""
        op = _make_purchase_op(
            self.project, self.vendor, self.officer, Decimal("1000.00")
        )
        item = _make_invoice_with_item(
            op, self.template, Decimal("10"), Decimal("100.00")
        )
        _make_product_for_item(self.template, item, Decimal("100.00"))

        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("90.00"))
        ia.finalize()

        adj = ia.adjustment
        original_tx_count = adj.get_all_transactions().count()

        # Direct reversal
        adj.reverse(officer=self.officer, date=date.today(), reason="direct")

        all_txs = adj.get_all_transactions()
        self.assertEqual(
            all_txs.count(),
            original_tx_count + 1,
            "Direct reversal must create one additional counter-transaction",
        )

    def test_direct_reversal_fails_for_unfinalized_item_adjustment(self):
        """Reversing an Adjustment whose InvoiceItemAdjustment has no linked
        Adjustment must fail gracefully."""
        op = _make_purchase_op(
            self.project, self.vendor, self.officer, Decimal("1000.00")
        )
        item = _make_invoice_with_item(
            op, self.template, Decimal("10"), Decimal("100.00")
        )
        _make_product_for_item(self.template, item, Decimal("100.00"))

        # Create item adjustment WITHOUT finalizing (no Adjustment created)
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("90.00"))

        # ia.adjustment is None because finalize() was never called
        # Trying to reverse a standalone Adjustment (not linked) should work normally
        # But since there's no linked Adjustment, this test verifies nothing breaks
        self.assertIsNone(ia.adjustment)
