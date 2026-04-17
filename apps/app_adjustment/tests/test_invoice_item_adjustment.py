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

from apps.app_adjustment._item_type import InvoiceItemAdjustmentType
from apps.app_adjustment.models import (
    AdjustmentType,
    InvoiceItemAdjustment,
    InvoiceItemAdjustmentLine,
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
from apps.app_transaction.transaction_type import TransactionType

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
        operation=operation, product=template, quantity=quantity, unit_price=unit_price
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


class FinalizationTest(TestCase):
    """finalize() creates the Adjustment with correct type/amount/effect,
    and the issuance transaction flows through to effective_amount."""

    def setUp(self):
        self.officer = _make_officer()
        self.project = _make_project()
        self.vendor = _make_vendor()
        _link_vendor(self.project, self.vendor)
        self.template = _make_product_template()

    def _purchase_setup(self, qty, price):
        op = _make_purchase_op(self.project, self.vendor, self.officer, qty * price)
        item = _make_invoice_with_item(op, self.template, qty, price)
        _make_product_for_item(self.template, item, price)
        return op, item

    def test_finalize_purchase_decrease_creates_correct_adjustment(self):
        op, item = self._purchase_setup(qty=Decimal("10"), price=Decimal("100.00"))
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        # price went down from 100 to 90
        _make_line(ia, item, new_unit_price=Decimal("90.00"))

        ia.finalize()

        self.assertIsNotNone(ia.adjustment)
        adj = ia.adjustment
        self.assertEqual(adj.type, AdjustmentType.PURCHASE_ITEM_CORRECTION_DECREASE)
        self.assertEqual(adj.amount, Decimal("100.00"))  # 10 * (100-90)

    def test_finalize_purchase_increase_creates_correct_adjustment(self):
        op, item = self._purchase_setup(qty=Decimal("5"), price=Decimal("200.00"))
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_INCREASE, self.officer
        )
        # price went up from 200 to 220
        _make_line(ia, item, new_unit_price=Decimal("220.00"))

        ia.finalize()

        adj = ia.adjustment
        self.assertEqual(adj.type, AdjustmentType.PURCHASE_ITEM_CORRECTION_INCREASE)
        self.assertEqual(adj.amount, Decimal("100.00"))  # 5 * (220-200)

    def test_finalize_reflects_in_effective_amount(self):
        op, item = self._purchase_setup(qty=Decimal("10"), price=Decimal("100.00"))
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("90.00"))
        ia.finalize()

        # original amount 1000, minus 100 discount
        self.assertEqual(op.effective_amount, Decimal("900.00"))

    def test_finalize_creates_issuance_transaction(self):
        op, item = self._purchase_setup(qty=Decimal("10"), price=Decimal("100.00"))
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("90.00"))
        ia.finalize()

        txn = ia.adjustment.get_all_transactions().get(
            type=TransactionType.PURCHASE_ADJUSTMENT_DECREASE
        )
        self.assertEqual(txn.amount, Decimal("100.00"))

    def test_finalize_raises_if_net_zero(self):
        op, item = self._purchase_setup(qty=Decimal("10"), price=Decimal("100.00"))
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        # no change — price stays the same
        _make_line(ia, item, new_unit_price=Decimal("100.00"))

        with self.assertRaises(ValidationError):
            ia.finalize()

    def test_finalize_raises_if_already_finalized(self):
        op, item = self._purchase_setup(qty=Decimal("10"), price=Decimal("100.00"))
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("90.00"))
        ia.finalize()

        with self.assertRaises(ValidationError):
            ia.finalize()


# ---------------------------------------------------------------------------
# LedgerEntryTest
# ---------------------------------------------------------------------------


class LedgerEntryTest(TestCase):
    """Saving a line creates the correct ProductLedgerEntry rows."""

    def setUp(self):
        self.officer = _make_officer()
        self.project = _make_project()
        self.vendor = _make_vendor()
        _link_vendor(self.project, self.vendor)
        self.client = _make_client()
        _link_client(self.project, self.client)
        self.template = _make_product_template()

    def _purchase_setup(self, qty, price):
        op = _make_purchase_op(self.project, self.vendor, self.officer, qty * price)
        item = _make_invoice_with_item(op, self.template, qty, price)
        product = _make_product_for_item(self.template, item, price)
        return op, item, product

    def _sale_setup(self, qty, price):
        op = _make_sale_op(self.client, self.project, self.officer, qty * price)
        item = _make_invoice_with_item(op, self.template, qty, price)
        product = _make_product_for_item(self.template, item, price)
        return op, item, product

    def test_purchase_price_decrease_ledger_entry(self):
        op, item, product = self._purchase_setup(
            qty=Decimal("10"), price=Decimal("100.00")
        )
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("90.00"))

        entry = ProductLedgerEntry.objects.filter(
            product=product, entry_type=ProductLedgerEntry.EntryType.ADJUSTMENT
        ).latest("id")

        self.assertEqual(entry.quantity_delta, Decimal("0.00"))
        self.assertEqual(entry.value_delta, Decimal("-100.00"))  # 10*(90-100)

    def test_purchase_quantity_decrease_ledger_entry(self):
        op, item, product = self._purchase_setup(
            qty=Decimal("10"), price=Decimal("100.00")
        )
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_quantity=Decimal("8.00"))

        entry = ProductLedgerEntry.objects.filter(
            product=product, entry_type=ProductLedgerEntry.EntryType.ADJUSTMENT
        ).latest("id")

        self.assertEqual(entry.quantity_delta, Decimal("-2.00"))
        self.assertEqual(entry.value_delta, Decimal("-200.00"))  # (8-10)*100

    def test_purchase_removal_ledger_entry(self):
        op, item, product = self._purchase_setup(
            qty=Decimal("5"), price=Decimal("200.00")
        )
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, is_removed=True)

        entry = ProductLedgerEntry.objects.filter(
            product=product, entry_type=ProductLedgerEntry.EntryType.ADJUSTMENT
        ).latest("id")

        self.assertEqual(entry.quantity_delta, Decimal("-5.00"))
        self.assertEqual(entry.value_delta, Decimal("-1000.00"))  # -(5*200)

    def test_sale_price_decrease_ledger_entry(self):
        op, item, product = self._sale_setup(qty=Decimal("4"), price=Decimal("50.00"))
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.SALE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, new_unit_price=Decimal("40.00"))

        entry = ProductLedgerEntry.objects.filter(
            product=product, entry_type=ProductLedgerEntry.EntryType.ADJUSTMENT
        ).latest("id")

        # SALE sign: val_sign = -1, so value_delta = (-40) * -1 = +40
        self.assertEqual(entry.quantity_delta, Decimal("0.00"))
        # value_delta of the line = 4*(40-50) = -40; SALE val_sign = -1 → stored as +40
        self.assertEqual(entry.value_delta, Decimal("40.00"))

    def test_sale_item_removal_ledger_entry(self):
        op, item, product = self._sale_setup(qty=Decimal("3"), price=Decimal("100.00"))
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.SALE_ITEM_DECREASE, self.officer
        )
        _make_line(ia, item, is_removed=True)

        entry = ProductLedgerEntry.objects.filter(
            product=product, entry_type=ProductLedgerEntry.EntryType.ADJUSTMENT
        ).latest("id")

        # removal value_delta = -(3*100) = -300; SALE val_sign=-1 → stored as +300
        self.assertEqual(entry.quantity_delta, Decimal("3.00"))
        self.assertEqual(entry.value_delta, Decimal("300.00"))

    def test_idempotency_key_prevents_duplicate_entries(self):
        op, item, product = self._purchase_setup(
            qty=Decimal("10"), price=Decimal("100.00")
        )
        ia = _make_item_adj(
            op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        line = _make_line(ia, item, new_unit_price=Decimal("90.00"))

        before = ProductLedgerEntry.objects.count()
        ProductLedgerEntry.record_adjustment_line(line)  # duplicate call
        after = ProductLedgerEntry.objects.count()
        self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# ValidationTest
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
        from apps.app_operation.models.proxies import ExpenseOperation

        world = Entity.create(EntityType.WORLD)
        op = ExpenseOperation.objects.create(
            source=self.project,
            destination=world,
            amount=Decimal("500.00"),
            operation_type=OperationType.EXPENSE,
            date=date.today(),
            officer=self.officer,
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
            # nothing set — is_removed=False, new_quantity=None, new_unit_price=None
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
# ImmutabilityTest
# ---------------------------------------------------------------------------


class ImmutabilityTest(TestCase):
    """Fields on both models cannot be changed after save."""

    def setUp(self):
        self.officer = _make_officer()
        self.project = _make_project()
        self.vendor = _make_vendor()
        _link_vendor(self.project, self.vendor)
        self.template = _make_product_template()
        self.op = _make_purchase_op(self.project, self.vendor, self.officer)
        self.item = _make_invoice_with_item(
            self.op, self.template, Decimal("10"), Decimal("100.00")
        )

    def test_item_adjustment_operation_is_immutable(self):
        ia = _make_item_adj(
            self.op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        other_op = _make_purchase_op(
            self.project, self.vendor, self.officer, Decimal("200.00")
        )
        ia.operation = other_op
        with self.assertRaises(ValidationError):
            ia.save()

    def test_item_adjustment_type_is_immutable(self):
        ia = _make_item_adj(
            self.op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        ia.type = InvoiceItemAdjustmentType.PURCHASE_ITEM_INCREASE
        with self.assertRaises(ValidationError):
            ia.save()

    def test_line_fields_are_immutable(self):
        ia = _make_item_adj(
            self.op, InvoiceItemAdjustmentType.PURCHASE_ITEM_DECREASE, self.officer
        )
        line = _make_line(ia, self.item, new_unit_price=Decimal("90.00"))
        line.new_unit_price = Decimal("80.00")
        with self.assertRaises(ValidationError):
            line.save()


# ---------------------------------------------------------------------------
# ReversalTest
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
            product=product, entry_type=ProductLedgerEntry.EntryType.ADJUSTMENT
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
