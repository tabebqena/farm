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
from apps.app_operation.models.proxies import DeathOperation, PurchaseOperation


class DeathReversalTest(TestCase):
    """Reversing a death reverses its auto-created movement lines, negates the
    ledger, and restores the dead product to ACTIVE (SE5/SE6/SE7)."""

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
        # DEATH applies to livestock — ANIMAL templates can die.
        self.template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
        )

    def _make_moved_product(self, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Create a physically-moved ACTIVE animal owned by the project."""
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

    def _record_death(self, product, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Record a death against an existing product via the full create pipeline."""
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
        return DeathOperation.create(
            operation_type=OperationType.DEATH,
            source=self.project_entity,
            destination=self.system_entity,
            amount=(qty * price).quantize(Decimal("0.01")),
            date=date.today(),
            description="Test death",
            officer=self.officer_user,
            amount_paid=Decimal("0.00"),
            raw_post=raw_post,
            project=self.project_entity,
        )

    def _make_dead(self, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Create a physically-moved ACTIVE animal and record its death."""
        product = self._make_moved_product(qty, price)
        op = self._record_death(product, qty, price)
        return op, product

    # ------------------------------------------------------------------
    # SE1 — reversal record
    # ------------------------------------------------------------------

    def test_reverse_creates_reversal_record(self):
        op, _ = self._make_dead()
        reversal = op.reverse(officer=self.officer_user, reason="test reversal")

        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, op)
        self.assertTrue(reversal.is_reversal)

    def test_reverse_marks_original_as_reversed(self):
        op, _ = self._make_dead()
        reversal = op.reverse(officer=self.officer_user, reason="test reversal")

        op.refresh_from_db()
        self.assertTrue(op.is_reversed)
        self.assertEqual(op.reversed_by, reversal)

    # ------------------------------------------------------------------
    # No accounting transactions
    # ------------------------------------------------------------------

    def test_reverse_creates_no_transactions(self):
        """Reversing a death must NOT create any counter-transactions."""
        op, _ = self._make_dead()
        op.reverse(officer=self.officer_user, reason="test reversal")

        self.assertEqual(op.get_all_transactions().count(), 0)
        self.assertEqual(op.reversed_by.get_all_transactions().count(), 0)

    # ------------------------------------------------------------------
    # SE6 — movement lines reversed
    # ------------------------------------------------------------------

    def test_reverse_reverses_auto_movement_lines(self):
        op, product = self._make_dead()

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

    # ------------------------------------------------------------------
    # SE5 — ledger negation
    # ------------------------------------------------------------------

    def test_reverse_negates_ledger_entries(self):
        op, product = self._make_dead()
        op.reverse(officer=self.officer_user, reason="test reversal")

        # Reversing the death negates the outbound movement — the product's
        # net presence is restored to the pre-death +5.
        state = movement_state(product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("5.00"))
        self.assertEqual(state["value"], Decimal("500.00"))

    def test_reverse_movement_ledger_negation_exact_set(self):
        """Every DEATH movement line must have an exact reversal counterpart
        (not just the first row), restoring the product's presence."""
        op, product = self._make_dead()
        op.reverse(officer=self.officer_user, reason="test reversal")

        originals = InventoryMovementLine.objects.filter(
            product=product, reversal_of__isnull=True
        )
        reversals = InventoryMovementLine.objects.filter(
            product=product, reversal_of__isnull=False
        )
        self.assertEqual(originals.count(), 2)  # purchase + death
        self.assertEqual(reversals.count(), 1)
        for rl in reversals:
            self.assertEqual(rl.quantity, Decimal("5.00"))
            self.assertIsNotNone(rl.reversal_of)
        state = movement_state(product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("5.00"))
        self.assertEqual(state["value"], Decimal("500.00"))

    # ------------------------------------------------------------------
    # SE7 — product status restored on reversal
    # ------------------------------------------------------------------

    def test_death_moves_product_to_dead_status(self):
        _, product = self._make_dead()
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.DEAD)

    def test_reversed_product_returns_to_active_status(self):
        op, product = self._make_dead()
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.DEAD)

        op.reverse(officer=self.officer_user, reason="test reversal")

        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)

    # ------------------------------------------------------------------
    # SE10 — constraints
    # ------------------------------------------------------------------

    def test_cannot_reverse_already_reversed_operation(self):
        op, _ = self._make_dead()
        op.reverse(officer=self.officer_user, reason="test reversal")
        op.refresh_from_db()

        with self.assertRaises(ValidationError):
            op.reverse(officer=self.officer_user)

    def test_cannot_reverse_a_reversal(self):
        op, _ = self._make_dead()
        reversal = op.reverse(officer=self.officer_user, reason="test reversal")

        with self.assertRaises(ValidationError):
            reversal.reverse(officer=self.officer_user)

    # ------------------------------------------------------------------
    # SR8 — differential invariant: create + reverse leaves the world unchanged
    # ------------------------------------------------------------------

    def test_create_then_reverse_leaves_world_unchanged(self):
        """SR8 — balances, payables, receivables and the ledger all return to
        the pre-operation state after a full death create + reverse cycle.

        The setup purchase is a permanent fixture (it moves the animal into the
        project's stock), so the snapshot is taken after the purchase and
        before the death — the death + reversal must leave that state intact."""
        from apps.app_operation.tests.base import (
            assert_derived_state_unchanged,
            snapshot_derived_state,
        )

        product = self._make_moved_product(
            qty=Decimal("5.00"), price=Decimal("100.00")
        )
        before = snapshot_derived_state()

        op = self._record_death(
            product, qty=Decimal("5.00"), price=Decimal("100.00")
        )
        op.reverse(officer=self.officer_user, reason="test reversal")

        assert_derived_state_unchanged(self, before, msg="death create+reverse")
