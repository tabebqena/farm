from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import (
    InventoryMovementLine,
    Product,
    ProductTemplate,
)
from apps.app_inventory.stock import movement_state
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import BirthOperation

User = get_user_model()


class BirthReversalTest(TestCase):
    """Reversing a birth reverses its auto-created movement lines and negates
    the ledger while the reversal record is created. No transactions are
    created (Birth is a stock event, not an accounting operation)."""

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )
        self.project_entity = Entity.create(
            EntityType.PROJECT, name="Test Farm Project"
        )
        self.template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
        )
        self.template.entities.add(self.project_entity)

    def _make_born(self, qty=Decimal("5.00"), price=Decimal("100.00")):
        raw_post = {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-product_template": str(self.template.pk),
            "items-0-quantity": str(qty),
            "items-0-unit_price": str(price),
            "items-0-description": "",
            "items-0-unique_id": "",
            "items-0-DELETE": "",
        }
        op = BirthOperation.create(
            operation_type=OperationType.BIRTH,
            source=self.system_entity,
            destination=self.project_entity,
            amount=(qty * price).quantize(Decimal("0.01")),
            date=date.today(),
            description="Test birth",
            officer=self.officer_user,
            amount_paid=Decimal("0.00"),
            raw_post=raw_post,
            project=self.project_entity,
        )
        product = op.movement_lines.first().product
        return op, product

    def test_reverse_creates_reversal_record(self):
        op, _ = self._make_born()
        reversal = op.reverse(officer=self.officer_user, reason="test reversal")

        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, op)
        self.assertTrue(reversal.is_reversal)

    def test_reverse_marks_original_as_reversed(self):
        op, _ = self._make_born()
        reversal = op.reverse(officer=self.officer_user, reason="test reversal")

        op.refresh_from_db()
        self.assertTrue(op.is_reversed)
        self.assertEqual(op.reversed_by, reversal)

    def test_reverse_creates_no_transactions(self):
        """Reversing a birth must NOT create any counter-transactions."""
        op, _ = self._make_born()
        op.reverse(officer=self.officer_user, reason="test reversal")

        self.assertEqual(op.get_all_transactions().count(), 0)
        reversal = op.reversed_by
        self.assertEqual(reversal.get_all_transactions().count(), 0)

    def test_reverse_reverses_auto_movement_lines(self):
        op, product = self._make_born()

        original_lines = op.movement_lines.filter(reversal_of__isnull=True)
        self.assertEqual(original_lines.count(), 5)
        op.reverse(officer=self.officer_user, reason="test reversal")

        reversal_lines = op.movement_lines.filter(reversal_of__isnull=False)
        self.assertEqual(reversal_lines.count(), 5)
        # Each per-head line is reversed with an equal-and-opposite line
        for rl in reversal_lines:
            self.assertIsNotNone(rl.reversal_of)
            self.assertEqual(rl.product, rl.reversal_of.product)
            self.assertEqual(rl.quantity, Decimal("1.00"))
        # The original lines are preserved (reversals link to them)
        self.assertEqual(
            op.movement_lines.filter(reversal_of__isnull=True).count(),
            5,
        )

    def test_reverse_negates_ledger_entries(self):
        op, product = self._make_born()
        op.reverse(officer=self.officer_user, reason="test reversal")

        # Reversing the birth negates the product's movement — net presence 0.
        state = movement_state(product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("0.00"))
        self.assertEqual(state["value"], Decimal("0.00"))

    # ------------------------------------------------------------------
    # SE5 — exact negation set: every BIRTH movement line has a REVERSAL mirror
    # ------------------------------------------------------------------

    def test_reverse_movement_ledger_negation_exact_set(self):
        """Every movement line must have an exact reversal counterpart (not just
        the first line) and each product's net presence returns to zero."""
        op, _ = self._make_born()
        product_ids = list(
            op.movement_lines.filter(reversal_of__isnull=True).values_list(
                "product_id", flat=True
            )
        )
        op.reverse(officer=self.officer_user, reason="test reversal")

        originals = InventoryMovementLine.objects.filter(
            product_id__in=product_ids, reversal_of__isnull=True
        )
        reversals = InventoryMovementLine.objects.filter(
            product_id__in=product_ids, reversal_of__isnull=False
        )
        self.assertEqual(originals.count(), 5)
        self.assertEqual(reversals.count(), 5)
        for rl in reversals:
            self.assertEqual(rl.quantity, Decimal("1.00"))
            self.assertIsNotNone(rl.reversal_of)
        for pid in product_ids:
            state = movement_state(Product.objects.get(pk=pid), as_of=date.today())
            self.assertEqual(state["quantity"], Decimal("0.00"))
            self.assertEqual(state["value"], Decimal("0.00"))

    # ------------------------------------------------------------------
    # SE7 — born products persist by design but are REMOVED after reversal
    # ------------------------------------------------------------------

    def test_reverse_born_products_removed_from_stock(self):
        """BIRTH lazily creates one product per head; reversing the birth does
        NOT delete them (audit trail) but marks each as REMOVED — no longer in
        stock and barred from new operations."""
        op, _ = self._make_born()
        product_ids = list(
            op.movement_lines.filter(reversal_of__isnull=True).values_list(
                "product_id", flat=True
            )
        )
        self.assertEqual(len(product_ids), 5)

        op.reverse(officer=self.officer_user, reason="test reversal")

        for pid in product_ids:
            product = Product.objects.get(pk=pid)
            self.assertEqual(product.status, Product.Status.REMOVED)
            # A REMOVED animal cannot be used in new operations.
            with self.assertRaises(ValidationError):
                product.validate_active()

    # ------------------------------------------------------------------
    # SR8 — differential invariant: create + reverse leaves the world unchanged
    # ------------------------------------------------------------------

    def test_create_then_reverse_leaves_world_unchanged(self):
        """SR8 — balances, payables, receivables and the ledger all return to
        the pre-operation state after a full birth create + reverse cycle."""
        from apps.app_operation.tests.base import (
            assert_derived_state_unchanged,
            snapshot_derived_state,
        )

        before = snapshot_derived_state()

        op, _ = self._make_born(qty=Decimal("5.00"), price=Decimal("100.00"))
        op.reverse(officer=self.officer_user, reason="test reversal")

        assert_derived_state_unchanged(self, before, msg="birth create+reverse")

    # ------------------------------------------------------------------
    # VR4 — reversal dependency guard (born products still ACTIVE)
    # ------------------------------------------------------------------

    def test_reversal_blocked_when_born_product_moved_again_in_later_death(self):
        """VR4 — reversing a birth is blocked once a born animal was moved
        again in a later non-reversed outbound operation (e.g. DEATH).

        Scenario: calf born (ACTIVE) → the same calf dies (DEATH, outbound
        movement). Reversing the birth would push the calf's net presence
        negative, so the dependency guard blocks it.
        """
        from apps.app_inventory.tests.general import (
            make_invoice_item,
            make_operation,
        )
        from apps.app_operation.models.proxies import DeathOperation

        op, product = self._make_born(qty=Decimal("1.00"), price=Decimal("100.00"))
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)

        # A later DEATH writes the same animal off stock (outbound movement).
        death = make_operation(
            self.project_entity,
            self.system_entity,
            self.officer_user,
            DeathOperation,
            OperationType.DEATH,
            amount=Decimal("100.00"),
        )
        item = make_invoice_item(
            death, self.template, Decimal("1"), Decimal("100.00")
        )
        InventoryMovementLine.objects.create(
            operation=death,
            invoice_item=item,
            product=product,
            quantity=Decimal("1.00"),
            date=date.today(),
            officer=self.officer_user,
        )
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.DEAD)

        with self.assertRaises(ValidationError):
            op.reverse(officer=self.officer_user, reason="test reversal")

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    def test_cannot_reverse_already_reversed_operation(self):
        op, _ = self._make_born()
        op.reverse(officer=self.officer_user, reason="test reversal")
        op.refresh_from_db()

        with self.assertRaises(ValidationError):
            op.reverse(officer=self.officer_user)

    def test_cannot_reverse_a_reversal(self):
        op, _ = self._make_born()
        reversal = op.reverse(officer=self.officer_user, reason="test reversal")

        with self.assertRaises(ValidationError):
            reversal.reverse(officer=self.officer_user)
