from collections import Counter
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import (
    Product,
    ProductLedgerEntry,
    ProductTemplate,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import BirthOperation
from apps.app_operation.tests.base import assert_tx_types
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


class BirthReversalTest(TestCase):
    """Reversing a birth reverses its auto-created movement lines and negates
    the ledger while the reversal record and counter-transactions are created."""

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

    def test_reverse_creates_counter_transactions(self):
        op, _ = self._make_born()
        op.reverse(officer=self.officer_user, reason="test reversal")

        # 2 originals + 2 counter-transactions, one per type
        counter = op.get_all_transactions().filter(reversal_of__isnull=False)
        self.assertEqual(counter.count(), 2)
        self.assertEqual(
            dict(
                Counter(counter.values_list("type", flat=True))
            ),
            {
                TransactionType.BIRTH_ISSUANCE: 1,
                TransactionType.BIRTH_PAYMENT: 1,
            },
        )

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
        item = op.items.get()
        op.reverse(officer=self.officer_user, reason="test reversal")

        # Each individually tracked product's movement is negated (-1.00)
        movement_reversal = ProductLedgerEntry.objects.filter(
            product=product,
            entry_type=ProductLedgerEntry.EntryType.REVERSAL,
        )
        self.assertEqual(movement_reversal.count(), 1)
        self.assertEqual(movement_reversal.first().quantity_delta, Decimal("-1.00"))

        # Issuance negation is written with product=None for the invoice item
        # (movement reversals carry their individual product, so disambiguate)
        issuance_reversal = ProductLedgerEntry.objects.filter(
            invoice_item=item,
            product__isnull=True,
            entry_type=ProductLedgerEntry.EntryType.REVERSAL,
        )
        self.assertEqual(
            issuance_reversal.count(), 1, "Negated issuance ledger entry missing"
        )
        self.assertEqual(issuance_reversal.first().quantity_delta, Decimal("-5.00"))

    # ------------------------------------------------------------------
    # SE5 — exact negation set: every BIRTH_MOVEMENT row has a REVERSAL mirror
    # ------------------------------------------------------------------

    def test_reverse_movement_ledger_negation_exact_set(self):
        """Every movement ledger row must have an exact -1.00 REVERSAL counterpart
        (not just the first row)."""
        op, _ = self._make_born()
        product_ids = list(
            op.movement_lines.filter(reversal_of__isnull=True).values_list(
                "product_id", flat=True
            )
        )
        op.reverse(officer=self.officer_user, reason="test reversal")

        originals = ProductLedgerEntry.objects.filter(
            product_id__in=product_ids,
            entry_type=ProductLedgerEntry.EntryType.BIRTH_MOVEMENT,
        )
        reversals = ProductLedgerEntry.objects.filter(
            product_id__in=product_ids,
            entry_type=ProductLedgerEntry.EntryType.REVERSAL,
        )
        self.assertEqual(originals.count(), 5)
        self.assertEqual(reversals.count(), 5)
        for entry in reversals:
            self.assertEqual(entry.quantity_delta, Decimal("-1.00"))
            self.assertEqual(entry.value_delta, Decimal("-100.00"))

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
