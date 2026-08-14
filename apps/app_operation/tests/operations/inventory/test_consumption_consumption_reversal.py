from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InventoryMovementLine,
    Product,
    ProductTemplate,
)
from apps.app_inventory.stock import movement_state
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

    def _purchase_product(self, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Return an ACTIVE, physically-moved product owned by the project."""
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
        return product

    def _consume(self, product, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Drive the ConsumptionOperation.create() pipeline for *qty* of a product."""
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
        return ConsumptionOperation.create(
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

    def _make_consumed(self, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Create a physically-moved ACTIVE product and consume it."""
        product = self._purchase_product(qty, price)
        op = self._consume(product, qty, price)
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
        op.reverse(officer=self.officer_user, reason="test reversal")

        # Reversing the consumption negates the outbound movement — the
        # product's net presence is restored to the pre-consumption +5.
        state = movement_state(product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("5.00"))

    def test_reverse_creates_no_transactions(self):
        op, _ = self._make_consumed()
        op.reverse(officer=self.officer_user, reason="test reversal")

        self.assertEqual(op.get_all_transactions().count(), 0)
        self.assertEqual(op.reversed_by.get_all_transactions().count(), 0)

    def test_reverse_movement_ledger_negation_exact_set(self):
        """Every CONSUMPTION movement line must have an exact reversal
        counterpart (not just the first row), restoring the presence."""
        op, product = self._make_consumed()
        op.reverse(officer=self.officer_user, reason="test reversal")

        originals = InventoryMovementLine.objects.filter(
            product=product, reversal_of__isnull=True
        )
        reversals = InventoryMovementLine.objects.filter(
            product=product, reversal_of__isnull=False
        )
        self.assertEqual(originals.count(), 2)  # purchase + consumption
        self.assertEqual(reversals.count(), 1)
        for rl in reversals:
            self.assertEqual(rl.quantity, Decimal("5.00"))
        state = movement_state(product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("5.00"))

    def test_reversed_product_returns_to_active_status(self):
        op, product = self._make_consumed()
        op.reverse(officer=self.officer_user, reason="test reversal")

        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)

    # ------------------------------------------------------------------
    # Inventory-value behaviour (no longer affects profit_loss directly)
    # ------------------------------------------------------------------

    def test_reverse_does_not_change_profit_loss(self):
        """Reversing a consumption must not change profit_loss() — the value
        effect flows through inventory value instead."""
        op, _ = self._make_consumed()
        profit_with_consumption = self.project_entity.profit_loss()

        op.reverse(officer=self.officer_user, reason="test reversal")

        self.assertEqual(
            self.project_entity.profit_loss(),
            profit_with_consumption,
            "Reversing a consumption must not change profit_loss().",
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

    # ------------------------------------------------------------------
    # VR4 — reversal dependency guard (partial consumption)
    # ------------------------------------------------------------------

    def test_reversal_blocked_when_product_moved_again_in_later_consumption(self):
        """VR4 — reversing a partial consumption is blocked once the same
        product is fully written off by a later consumption.

        Scenario: 5 kg on-hand → consume 2 (product still ACTIVE) → consume the
        remaining 3 (product CONSUMED). Reversing the first consumption would
        resurrect stock that was later consumed, so the dependency guard blocks it.
        """
        product = self._purchase_product(qty=Decimal("5.00"))
        first = self._consume(product, qty=Decimal("2.00"))
        # Product stays ACTIVE with 3 kg remaining after the partial consumption.
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)

        # Second consumption writes off the remaining 3 kg → CONSUMED.
        self._consume(product, qty=Decimal("3.00"))
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.CONSUMED)

        with self.assertRaises(ValidationError):
            first.reverse(officer=self.officer_user)

    # ------------------------------------------------------------------
    # VR1 / VR2 — already-reversed and is-a-reversal guards
    # ------------------------------------------------------------------

    def test_cannot_reverse_already_reversed_operation(self):
        """VR1 — reversing an already-reversed consumption is rejected."""
        op, _ = self._make_consumed()
        op.reverse(officer=self.officer_user, reason="test reversal")
        op.refresh_from_db()

        with self.assertRaises(ValidationError):
            op.reverse(officer=self.officer_user)

    def test_cannot_reverse_a_reversal(self):
        """VR2 — a reversal record cannot itself be reversed."""
        op, _ = self._make_consumed()
        reversal = op.reverse(officer=self.officer_user, reason="test reversal")

        with self.assertRaises(ValidationError):
            reversal.reverse(officer=self.officer_user)

    # ------------------------------------------------------------------
    # SR10 — differential invariant: create + reverse leaves the world unchanged
    # ------------------------------------------------------------------

    def test_create_then_reverse_leaves_world_unchanged(self):
        """SR10 — balances, payables, receivables, ledger totals and inventory
        value all return to the pre-consumption state after a full
        create + reverse cycle.

        The setup purchase is a permanent fixture (it moves the feed into the
        project's stock), so the snapshot is taken after the purchase and before
        the consumption — the consumption + reversal must leave that state intact."""
        from apps.app_inventory.stock import inventory_value

        from apps.app_operation.tests.base import (
            assert_derived_state_unchanged,
            snapshot_derived_state,
        )

        product = self._purchase_product(qty=Decimal("5.00"), price=Decimal("100.00"))
        before = snapshot_derived_state()
        value_before = inventory_value(self.project_entity, as_of=date.today())
        self.assertEqual(value_before, Decimal("500.00"))

        op = self._consume(product, qty=Decimal("5.00"), price=Decimal("100.00"))
        op.reverse(officer=self.officer_user, reason="test reversal")

        assert_derived_state_unchanged(self, before, msg="consumption create+reverse")
        self.assertEqual(
            inventory_value(self.project_entity, as_of=date.today()),
            value_before,
            "Inventory value must be restored after create+reverse.",
        )
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)
