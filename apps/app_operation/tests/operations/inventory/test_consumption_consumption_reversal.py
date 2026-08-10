from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InventoryMovementLine,
    Product,
    ProductLedgerEntry,
    ProductTemplate,
)
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_project_entity,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import ConsumptionOperation, PurchaseOperation


class ConsumptionReversalTest(TestCase):
    """Reversing a consumption reverses its auto-created movement lines,
    negates the ledger, and restores the product to ACTIVE."""

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = make_user()
        self.project_entity = make_project_entity("Test Farm Project")
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        Stakeholder.objects.create(
            parent=self.project_entity,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.template = ProductTemplate.objects.create(
            name="Feed Mix",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
        )

    def _make_consumed(self, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Create a physically-moved ACTIVE product and consume it."""
        purchase = make_operation(
            self.project_entity,
            self.vendor,
            self.officer_user,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=(qty * price).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(purchase, self.template, qty, price)
        product = Product.objects.create(
            product_template=self.template,
            entity=self.project_entity,
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
            officer=self.officer_user,
        )

        raw_post = {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-quantity": str(qty),
            "items-0-unit_price": str(price),
            "items-0-description": "",
            "items-0-selected_product": str(product.pk),
            "items-0-DELETE": "",
        }
        op = ConsumptionOperation.create(
            operation_type=OperationType.CONSUMPTION,
            source=self.project_entity,
            destination=self.system_entity,
            amount=(qty * price).quantize(Decimal("0.01")),
            date=date.today(),
            description="Test consumption",
            officer=self.officer_user,
            amount_paid=Decimal("0.00"),
            raw_post=raw_post,
            project=self.project_entity,
        )
        return op, product

    def test_reverse_creates_reversal_record(self):
        op, _ = self._make_consumed()
        reversal = op.reverse(officer=self.officer_user, reason="test reversal")

        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, op)
        self.assertTrue(reversal.is_reversal)

    def test_reverse_reverses_auto_movement_lines(self):
        op, product = self._make_consumed()

        original_ml = op.movement_lines.get(reversal_of__isnull=True)
        op.reverse(officer=self.officer_user, reason="test reversal")

        # A reversal line is created that points back at the original line
        reversal_ml = op.movement_lines.get(reversal_of__isnull=False)
        self.assertEqual(reversal_ml.reversal_of, original_ml)
        self.assertEqual(reversal_ml.product, product)
        self.assertEqual(reversal_ml.quantity, Decimal("5.00"))
        # The original line is preserved (the reversal links to it)
        self.assertEqual(
            op.movement_lines.filter(reversal_of__isnull=True).count(),
            1,
        )

    def test_reverse_negates_ledger_entries(self):
        op, product = self._make_consumed()
        item = op.items.get()
        op.reverse(officer=self.officer_user, reason="test reversal")

        # Movement negation is linked to the product (qty +5.00 to undo -5.00)
        movement_reversal = ProductLedgerEntry.objects.filter(
            product=product,
            entry_type=ProductLedgerEntry.EntryType.REVERSAL,
        )
        self.assertTrue(movement_reversal.exists())
        self.assertEqual(movement_reversal.first().quantity_delta, Decimal("5.00"))

        # Issuance negation is written with product=None for the invoice item
        issuance_reversal = ProductLedgerEntry.objects.filter(
            invoice_item=item,
            entry_type=ProductLedgerEntry.EntryType.REVERSAL,
        )
        self.assertTrue(
            issuance_reversal.exists(),
            "Negated issuance ledger entry missing",
        )
        self.assertEqual(issuance_reversal.first().quantity_delta, Decimal("5.00"))

    def test_reverse_creates_counter_transactions(self):
        op, _ = self._make_consumed()
        op.reverse(officer=self.officer_user, reason="test reversal")

        counter = op.get_all_transactions().filter(reversal_of__isnull=False)
        self.assertEqual(counter.count(), 2)

    def test_reversed_product_returns_to_active_status(self):
        op, product = self._make_consumed()
        op.reverse(officer=self.officer_user, reason="test reversal")

        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)

    # ------------------------------------------------------------------
    # COGS / P&L behaviour (Option B)
    # ------------------------------------------------------------------

    def test_reverse_restores_profit_loss(self):
        """Reversing a consumption must negate its COGS effect and restore profit."""
        op, _ = self._make_consumed()
        profit_with_consumption = self.project_entity.profit_loss()

        op.reverse(officer=self.officer_user, reason="test reversal")

        self.assertEqual(
            self.project_entity.profit_loss(),
            profit_with_consumption + Decimal("500.00"),
            "A reversed consumption must no longer reduce profit.",
        )

    def test_reverse_keeps_fund_balance_unchanged(self):
        """Option B: consumption and its reversal are both non-cash for balance_at()."""
        op, _ = self._make_consumed()
        balance = self.project_entity.balance_at(date.today())

        op.reverse(officer=self.officer_user, reason="test reversal")

        self.assertEqual(
            self.project_entity.balance_at(date.today()),
            balance,
            "Neither consumption nor its reversal may change the fund balance.",
        )
