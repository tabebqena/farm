from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import Product, ProductTemplate
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalLossOperation
from apps.app_operation.tests.base import (
    assert_derived_state_unchanged,
    snapshot_derived_state,
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


class CapitalLossReversalTest(TestCase):
    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)

        self.officer_user = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )

        self.project_entity = Entity.create(EntityType.PROJECT, name="Test Project")

        self.op = CapitalLossOperation(
            source=self.project_entity,
            destination=self.system_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.CAPITAL_LOSS,
            date=date.today(),
            description="Test capital loss",
            officer=self.officer_user,
        )
        self.op.save()

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_reverse_creates_reversal_operation(self):
        reversal = self.op.reverse(officer=self.officer_user)

        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, self.op)

    def test_reverse_marks_original_as_reversed(self):
        reversal = self.op.reverse(officer=self.officer_user)

        self.op.refresh_from_db()
        self.assertTrue(self.op.is_reversed)
        self.assertEqual(self.op.reversed_by, reversal)

    def test_reversal_is_reversal(self):
        reversal = self.op.reverse(officer=self.officer_user)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reverse_inherits_amount_source_destination(self):
        reversal = self.op.reverse(officer=self.officer_user)

        self.assertEqual(reversal.amount, self.op.amount)
        self.assertEqual(reversal.source, self.op.source)
        self.assertEqual(reversal.destination, self.op.destination)

    def test_reverse_creates_no_transactions(self):
        """Reversing a capital loss must NOT create any counter-transactions."""
        self.op.reverse(officer=self.officer_user)
        self.assertEqual(self.op.get_all_transactions().count(), 0)
        self.assertEqual(self.op.reversed_by.get_all_transactions().count(), 0)

    def test_project_fund_unchanged_after_reversal(self):
        """A capital loss is non-cash, so reversing it must not change the fund."""
        balance_after_loss = self.project_entity.balance
        self.op.reverse(officer=self.officer_user)

        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            balance_after_loss,
            "Reversing a non-cash loss leaves the fund balance unchanged.",
        )

    # ------------------------------------------------------------------
    # Differential invariant — create + reverse leaves the world unchanged
    # ------------------------------------------------------------------

    def test_create_then_reverse_leaves_world_unchanged(self):
        """Balances, payables, receivables and ledger must all return to the
        pre-operation state after a full create + reverse cycle."""
        before = snapshot_derived_state()

        op = CapitalLossOperation(
            source=self.project_entity,
            destination=self.system_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.CAPITAL_LOSS,
            date=date.today(),
            description="Test capital loss",
            officer=self.officer_user,
        )
        op.save()
        op.reverse(officer=self.officer_user)

        assert_derived_state_unchanged(self, before, msg="capital loss create+reverse")

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    def test_cannot_reverse_already_reversed_operation(self):
        self.op.reverse(officer=self.officer_user)
        self.op.refresh_from_db()

        with self.assertRaises(ValidationError):
            self.op.reverse(officer=self.officer_user)

    def test_cannot_reverse_a_reversal(self):
        reversal = self.op.reverse(officer=self.officer_user)

        with self.assertRaises(ValidationError):
            reversal.reverse(officer=self.officer_user)


# ---------------------------------------------------------------------------
# SE7 — capital loss is value-only, product status never mutates
# ---------------------------------------------------------------------------


class CapitalLossReversalProductStatusTest(TestCase):
    """CAPITAL_LOSS writes down value only; it must never change a linked
    product's status, either on create or on reversal (SE7)."""

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )
        self.project_entity = Entity.create(EntityType.PROJECT, name="Test Project")
        self.template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
        )

    def _make_linked_product(self, amount=Decimal("500.00")):
        op = CapitalLossOperation(
            source=self.project_entity,
            destination=self.system_entity,
            amount=amount,
            operation_type=OperationType.CAPITAL_LOSS,
            date=date.today(),
            description="Test capital loss",
            officer=self.officer_user,
        )
        op.save()
        product = Product.objects.create(
            product_template=self.template,
            entity=self.project_entity,
            unit_price=amount,
            quantity=1,
        )
        op.add_valuation(
            product=product, amount=-amount, officer=self.officer_user
        )
        return op, product

    def test_loss_and_reversal_keep_product_active(self):
        """The linked product stays ACTIVE through create + reverse — the loss
        is a value write-down, not a status transition."""
        op, product = self._make_linked_product()
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)

        op.reverse(officer=self.officer_user)

        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)
