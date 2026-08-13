from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import InventoryMovementLine, InvoiceItem, ProductTemplate
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalGainOperation, PurchaseOperation
from apps.app_operation.tests.base import (
    assert_derived_state_unchanged,
    snapshot_derived_state,
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username="officer"):
    return User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def _make_person_entity(name):
    return Entity.create(EntityType.PERSON, name=name)
    return person.entity


def _make_project_entity(name):
    return Entity.create(EntityType.PROJECT, name=name)


def _make_vendor_entity(name):
    return Entity.create(EntityType.PERSON, name=name, is_vendor=True)


def _inject_project(system_entity, dest_entity, amount, officer_user):
    """Seed a Project entity's fund via CapitalGain."""
    CapitalGainOperation(
        source=system_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=date.today(),
        description="Seed project balance",
        officer=officer_user,
    ).save()


def _make_vendor_stakeholder(project_entity, vendor_entity, active=True):
    sh = Stakeholder(
        parent=project_entity,
        target=vendor_entity,
        role=StakeholderRole.VENDOR,
        active=active,
    )
    sh.save()
    return sh


# ---------------------------------------------------------------------------
# PurchaseCreateTest
# ---------------------------------------------------------------------------


class PurchaseReversalTest(TestCase):
    """
    Tests for purchase operation reversal.

    Reversal is allowed only when no PURCHASE_PAYMENT transactions exist.
    Reversing the operation creates a counter-transaction for the issuance.
    Since PURCHASE_ISSUANCE is non-cash, the project fund balance is unaffected
    both before and after reversal.
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = _make_officer()

        self.project_entity = _make_project_entity("Farm Project")
        _inject_project(
            self.system_entity,
            self.project_entity,
            Decimal("5000.00"),
            self.officer_user,
        )

        self.vendor_entity = _make_vendor_entity("Agri Supplies Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

        self.op = PurchaseOperation(
            source=self.project_entity,
            destination=self.vendor_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PURCHASE,
            date=date.today(),
            description="Test purchase",
            officer=self.officer_user,
        )
        self.op.save()

    # ------------------------------------------------------------------
    # Happy path — no payments, reversal allowed
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

    def test_reversal_is_marked_as_reversal(self):
        reversal = self.op.reverse(officer=self.officer_user)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reverse_inherits_amount_source_destination(self):
        reversal = self.op.reverse(officer=self.officer_user)

        self.assertEqual(reversal.amount, self.op.amount)
        self.assertEqual(reversal.source, self.op.source)
        self.assertEqual(reversal.destination, self.op.destination)

    def test_reverse_creates_counter_transaction_for_issuance(self):
        """Only the PURCHASE_ISSUANCE is implicitly reversed (not one-shot operation)."""
        self.op.reverse(officer=self.officer_user)

        all_txs = self.op.get_all_transactions()
        # 1 original PURCHASE_ISSUANCE + 1 counter-PURCHASE_ISSUANCE
        self.assertEqual(all_txs.count(), 2)

        counter_txs = all_txs.filter(reversal_of__isnull=False)
        self.assertEqual(counter_txs.count(), 1)

    def test_reverse_counter_transaction_flips_funds(self):
        self.op.reverse(officer=self.officer_user)

        original_tx = self.op.get_all_transactions().get(reversal_of__isnull=True)
        counter_tx = original_tx.reversed_by

        self.assertEqual(counter_tx.source, original_tx.target)
        self.assertEqual(counter_tx.target, original_tx.source)
        self.assertEqual(counter_tx.amount, original_tx.amount)

    def test_project_fund_unchanged_after_reversal(self):
        """Issuance is non-cash; reversing it leaves the project fund balance untouched."""
        balance_before_reversal = self.project_entity.balance

        self.op.reverse(officer=self.officer_user)

        self.project_entity.refresh_from_db()
        self.assertEqual(self.project_entity.balance, balance_before_reversal)

    # ------------------------------------------------------------------
    # SE4 — payables / receivables restored on reversal (regression class:
    # reversal mirrors must not leak into the obligation buckets)
    # ------------------------------------------------------------------

    def test_reverse_restores_project_payables(self):
        """PURCHASE_ISSUANCE makes the project owe the vendor; reversal clears it."""
        self.assertEqual(self.project_entity.payables, Decimal("1000.00"))
        self.op.reverse(officer=self.officer_user)

        self.assertEqual(self.project_entity.payables, Decimal("0.00"))

    def test_reverse_restores_vendor_receivables(self):
        """PURCHASE_ISSUANCE makes the vendor owed by the project; reversal clears it."""
        self.assertEqual(self.vendor_entity.receivables, Decimal("1000.00"))
        self.op.reverse(officer=self.officer_user)

        self.assertEqual(self.vendor_entity.receivables, Decimal("0.00"))

    def test_reverse_project_receivables_unchanged(self):
        self.op.reverse(officer=self.officer_user)

        self.assertEqual(self.project_entity.receivables, Decimal("0.00"))

    def test_reverse_vendor_payables_unchanged(self):
        self.op.reverse(officer=self.officer_user)

        self.assertEqual(self.vendor_entity.payables, Decimal("0.00"))

    # ------------------------------------------------------------------
    # Differential invariant — create + reverse leaves the world unchanged
    # ------------------------------------------------------------------

    def test_create_then_reverse_leaves_world_unchanged(self):
        """Balances, payables, receivables and ledger must all return to the
        pre-operation state after a full create + reverse cycle."""
        before = snapshot_derived_state()

        op = PurchaseOperation(
            source=self.project_entity,
            destination=self.vendor_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PURCHASE,
            date=date.today(),
            description="Test purchase",
            officer=self.officer_user,
        )
        op.save()
        op.reverse(officer=self.officer_user)

        assert_derived_state_unchanged(self, before, msg="purchase create+reverse")

    # ------------------------------------------------------------------
    # Reversal blocked by existing payment
    # ------------------------------------------------------------------

    def test_reversal_blocked_when_payment_exists(self):
        self.op.create_payment_transaction(
            amount=Decimal("500.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        with self.assertRaises(ValidationError):
            self.op.reverse(officer=self.officer_user)

    # ------------------------------------------------------------------
    # Reversal allowed once all payments are reversed
    # ------------------------------------------------------------------

    def test_reversible_after_payment_reversed(self):
        """A purchase becomes reversible once its payment is reversed."""
        self.op.create_payment_transaction(
            amount=Decimal("500.00"),
            officer=self.officer_user,
            date=date.today(),
        )
        payment_tx = self.op.get_all_transactions().get(
            type=TransactionType.PURCHASE_PAYMENT
        )
        payment_tx.reverse(officer=self.officer_user)

        reversal = self.op.reverse(officer=self.officer_user)

        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, self.op)

    def test_reversible_after_payment_reversed_counter_for_issuance_only(self):
        """SR5: only the issuance gets an implicit counter-transaction even when
        a (now-reversed) payment exists — the payment counter already exists."""
        self.op.create_payment_transaction(
            amount=Decimal("500.00"),
            officer=self.officer_user,
            date=date.today(),
        )
        payment_tx = self.op.get_all_transactions().get(
            type=TransactionType.PURCHASE_PAYMENT
        )
        payment_tx.reverse(officer=self.officer_user)
        self.op.reverse(officer=self.officer_user)

        all_txs = self.op.get_all_transactions()
        # original issuance + payment, plus the payment counter + issuance counter
        self.assertEqual(all_txs.count(), 4)
        counters = all_txs.filter(reversal_of__isnull=False)
        self.assertEqual(counters.count(), 2)
        self.assertEqual(
            {c.type for c in counters},
            {TransactionType.PURCHASE_ISSUANCE, TransactionType.PURCHASE_PAYMENT},
        )

    def test_pay_reverse_payment_then_reverse_op_leaves_world_unchanged(self):
        """Differential invariant: pay → reverse payment → reverse op returns the
        world to the pre-operation state."""
        before = snapshot_derived_state()

        op = PurchaseOperation(
            source=self.project_entity,
            destination=self.vendor_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PURCHASE,
            date=date.today(),
            description="Test purchase",
            officer=self.officer_user,
        )
        op.save()
        op.create_payment_transaction(
            amount=Decimal("500.00"),
            officer=self.officer_user,
            date=date.today(),
        )
        payment_tx = op.get_all_transactions().get(
            type=TransactionType.PURCHASE_PAYMENT
        )
        payment_tx.reverse(officer=self.officer_user)
        op.reverse(officer=self.officer_user)

        assert_derived_state_unchanged(
            self, before, msg="purchase pay+reverse-payment+reverse"
        )

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
# PurchaseReversalAfterMovementsTest — reversal unlocked once all movements are
# reversed (regression: the guard must count only active movement lines, not
# reversed originals).
# ---------------------------------------------------------------------------


class PurchaseReversalAfterMovementsTest(TestCase):
    """A purchase that received goods becomes reversible once every received
    movement line has been reversed by the user."""

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = _make_officer()

        self.project_entity = _make_project_entity("Farm Project")
        _inject_project(
            self.system_entity,
            self.project_entity,
            Decimal("5000.00"),
            self.officer_user,
        )

        self.vendor_entity = _make_vendor_entity("Agri Supplies Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

        self.template = ProductTemplate.objects.create(
            name="Feed Corn",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Grain",
            tracking_mode=ProductTemplate.TrackingMode.COMMODITY,
            default_unit="kg",
        )
        self.template.entities.add(self.project_entity)

    def _make_received_purchase(self):
        """A saved purchase with one invoice item and one received movement line."""
        op = PurchaseOperation(
            source=self.project_entity,
            destination=self.vendor_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PURCHASE,
            date=date.today(),
            description="Test purchase with receipt",
            officer=self.officer_user,
        )
        op.save()
        item = InvoiceItem.objects.create(
            operation=op,
            product_template=self.template,
            quantity=Decimal("10.00"),
            unit_price=Decimal("100.00"),
        )
        line = InventoryMovementLine.objects.create(
            operation=op,
            invoice_item=item,
            product=None,  # lazily created by save()
            quantity=Decimal("10.00"),
            date=date.today(),
            officer=self.officer_user,
        )
        return op, item, line

    def test_reversal_blocked_while_movement_active(self):
        op, item, line = self._make_received_purchase()

        with self.assertRaises(ValidationError):
            op.reverse(officer=self.officer_user)

    def test_reversible_after_all_movements_reversed(self):
        """Reversing every received movement unlocks the operation reversal."""
        op, item, line = self._make_received_purchase()

        line.reverse(officer=self.officer_user)

        reversal = op.reverse(officer=self.officer_user)
        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, op)

    def test_reverse_after_movements_reversed_leaves_world_unchanged(self):
        """Differential invariant: receive → reverse movements → reverse op
        returns balances, payables, receivables and ledger to the pre-op state."""
        before = snapshot_derived_state()

        op, item, line = self._make_received_purchase()
        line.reverse(officer=self.officer_user)
        op.reverse(officer=self.officer_user)

        assert_derived_state_unchanged(
            self, before, msg="purchase receive+reverse-movements+reverse"
        )
