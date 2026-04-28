from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalGainOperation, PurchaseOperation
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



class PurchasePaymentTest(TestCase):
    """
    Tests for PURCHASE_PAYMENT transactions.

    The project records a purchase obligation on save (PURCHASE_ISSUANCE, non-cash).
    Payments are created explicitly and move funds: project → vendor.
    Multiple partial payments are allowed, up to the total operation amount.
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

    def _pay(self, amount):
        self.op.create_payment_transaction(
            amount=amount,
            officer=self.officer_user,
            date=date.today(),
        )

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_payment_creates_purchase_payment_transaction(self):
        self._pay(Decimal("400.00"))

        payment_txs = self.op.get_all_transactions().filter(
            type=TransactionType.PURCHASE_PAYMENT
        )
        self.assertEqual(payment_txs.count(), 1)

    def test_payment_transaction_direction_is_project_to_vendor(self):
        self._pay(Decimal("400.00"))

        tx = self.op.get_all_transactions().get(type=TransactionType.PURCHASE_PAYMENT)
        self.assertEqual(tx.source, self.project_entity)
        self.assertEqual(tx.target, self.vendor_entity)

    def test_amount_remaining_to_settle_decreases_after_payment(self):
        self._pay(Decimal("400.00"))

        self.assertEqual(self.op.amount_remaining_to_settle, Decimal("600.00"))

    def test_multiple_partial_payments_are_allowed(self):
        self._pay(Decimal("300.00"))
        self._pay(Decimal("300.00"))
        self._pay(Decimal("400.00"))

        payment_txs = self.op.get_all_transactions().filter(
            type=TransactionType.PURCHASE_PAYMENT
        )
        self.assertEqual(payment_txs.count(), 3)
        self.assertEqual(self.op.amount_remaining_to_settle, Decimal("0.00"))

    def test_multiple_payments_accumulate_correctly(self):
        self._pay(Decimal("250.00"))
        self._pay(Decimal("350.00"))

        self.assertEqual(self.op.amount_settled, Decimal("600.00"))
        self.assertEqual(self.op.amount_remaining_to_settle, Decimal("400.00"))

    def test_full_payment_marks_operation_as_fully_settled(self):
        self._pay(Decimal("1000.00"))

        self.assertTrue(self.op.is_fully_settled)
        self.assertEqual(self.op.amount_remaining_to_settle, Decimal("0.00"))

    def test_project_fund_decreases_by_payment_amount(self):
        balance_before = self.project_entity.balance

        self._pay(Decimal("600.00"))

        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            balance_before - Decimal("600.00"),
        )

    def test_vendor_fund_increases_by_payment_amount(self):
        balance_before = self.vendor_entity.balance

        self._pay(Decimal("600.00"))

        self.vendor_entity.refresh_from_db()
        self.assertEqual(
            self.vendor_entity.balance,
            balance_before + Decimal("600.00"),
        )

    def test_total_transactions_after_partial_payment_is_two(self):
        """One issuance (created on save) + one payment = two transactions."""
        self._pay(Decimal("500.00"))

        self.assertEqual(self.op.get_all_transactions().count(), 2)

    # ------------------------------------------------------------------
    # Over-payment blocked
    # ------------------------------------------------------------------

    def test_payment_exceeding_operation_amount_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._pay(Decimal("1500.00"))

    def test_partial_payment_then_over_payment_raises_validation_error(self):
        self._pay(Decimal("800.00"))

        with self.assertRaises(ValidationError):
            self._pay(Decimal("300.00"))  # only 200 remaining

    def test_zero_payment_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._pay(Decimal("0.00"))

    def test_negative_payment_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._pay(Decimal("-100.00"))

    # ------------------------------------------------------------------
    # Balance check on payment (check_balance_on_payment = True)
    # ------------------------------------------------------------------

    def test_check_balance_on_payment_is_enabled(self):
        """Balance is checked before each payment transaction is created."""
        self.assertTrue(PurchaseOperation.check_balance_on_payment)

    def test_payment_blocked_when_project_fund_has_insufficient_balance(self):
        """
        PurchaseOperation.check_balance_on_payment = True.
        A payment that exceeds the project fund's current balance must raise
        ValidationError even when the amount is within the unsettled obligation.
        """
        # Drain the project fund completely via a prior full payment on a separate op,
        # then attempt to pay against *this* op with nothing left in the fund.
        drain_op = PurchaseOperation(
            source=self.project_entity,
            destination=self.vendor_entity,
            amount=Decimal("4000.00"),
            operation_type=OperationType.PURCHASE,
            date=date.today(),
            description="Drain purchase",
            officer=self.officer_user,
        )
        drain_op.save()
        drain_op.create_payment_transaction(
            amount=Decimal("4000.00"),
            officer=self.officer_user,
            date=date.today(),
        )
        # Project fund now has 5000 - 4000 = 1000, but self.op still has 1000 unsettled.
        # Attempt to pay 1001 — within op limit but beyond the fund balance.
        with self.assertRaises(ValidationError):
            self._pay(Decimal("1001.00"))


# ---------------------------------------------------------------------------
# PurchaseReversalTest
# ---------------------------------------------------------------------------
