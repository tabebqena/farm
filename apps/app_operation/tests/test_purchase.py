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


class PurchaseCreateTest(TestCase):
    """
    Tests for purchase operation creation: validation, issuance transaction, and
    fund behaviour.

    On save, only a PURCHASE_ISSUANCE transaction is created (obligation record).
    PURCHASE_ISSUANCE is a non-cash transaction — it does NOT affect fund balances.
    Cash movement only happens later via create_payment_transaction().
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = _make_officer()

        self.project_entity = _make_project_entity("Test Farm Project")
        _inject_project(
            self.system_entity,
            self.project_entity,
            Decimal("5000.00"),
            self.officer_user,
        )

        self.vendor_entity = _make_vendor_entity("Agri Supplies Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.project_entity,
            destination=self.vendor_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PURCHASE,
            date=date.today(),
            description="Test purchase",
            officer=self.officer_user,
        )
        defaults.update(kwargs)
        return PurchaseOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path — issuance only on creation
    # ------------------------------------------------------------------

    def test_save_creates_exactly_one_issuance_transaction(self):
        op = self._make_op()
        op.save()

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 1)
        self.assertTrue(
            transactions.filter(type=TransactionType.PURCHASE_ISSUANCE).exists(),
            "Issuance transaction must be created on save",
        )

    def test_no_payment_transaction_created_on_save(self):
        op = self._make_op()
        op.save()

        self.assertFalse(
            op.get_all_transactions()
            .filter(type=TransactionType.PURCHASE_PAYMENT)
            .exists(),
            "Payment transaction must NOT be created on save — purchase is not one-shot",
        )

    def test_issuance_transaction_direction_is_project_to_vendor(self):
        op = self._make_op()
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.PURCHASE_ISSUANCE)
        self.assertEqual(tx.source, self.project_entity.fund)
        self.assertEqual(tx.target, self.vendor_entity.fund)

    def test_issuance_transaction_amount_matches_operation(self):
        op = self._make_op(amount=Decimal("750.00"))
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.PURCHASE_ISSUANCE)
        self.assertEqual(tx.amount, Decimal("750.00"))

    def test_project_fund_balance_unchanged_after_save(self):
        """PURCHASE_ISSUANCE is non-cash; it does not affect fund balances."""
        balance_before = self.project_entity.fund.balance

        op = self._make_op(amount=Decimal("800.00"))
        op.save()

        self.project_entity.fund.refresh_from_db()
        self.assertEqual(self.project_entity.fund.balance, balance_before)

    def test_amount_remaining_to_settle_equals_full_amount_after_creation(self):
        op = self._make_op(amount=Decimal("1200.00"))
        op.save()

        self.assertEqual(op.amount_remaining_to_settle, Decimal("1200.00"))

    def test_is_not_fully_settled_after_creation(self):
        op = self._make_op()
        op.save()

        self.assertFalse(op.is_fully_settled)

    # ------------------------------------------------------------------
    # Source validation
    # ------------------------------------------------------------------

    def test_source_must_be_a_project_entity(self):
        non_project = _make_person_entity("Not A Project")
        op = self._make_op(source=non_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_must_be_active(self):
        self.project_entity.active = False
        self.project_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_fund_must_be_active(self):
        self.project_entity.fund.active = False
        self.project_entity.fund.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation
    # ------------------------------------------------------------------

    def test_destination_must_be_a_vendor_entity(self):
        non_vendor = _make_person_entity("Not A Vendor")
        op = self._make_op(destination=non_vendor)
        with self.assertRaises(ValidationError):
            op.save()

    # BUG the vendor can be a project
    def test_destination_project_entity_raises_validation_error(self):
        other_project = _make_project_entity("Some Project")
        op = self._make_op(destination=other_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_active_stakeholder_vendor(self):
        unregistered_vendor = _make_vendor_entity("Unregistered Vendor")
        # is_vendor=True but no Stakeholder relationship with this project
        op = self._make_op(destination=unregistered_vendor)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_with_inactive_stakeholder_raises_validation_error(self):
        inactive_vendor = _make_vendor_entity("Inactive Vendor")
        _make_vendor_stakeholder(self.project_entity, inactive_vendor, active=False)

        op = self._make_op(destination=inactive_vendor)
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Amount validation
    # ------------------------------------------------------------------

    def test_amount_zero_raises_validation_error(self):
        op = self._make_op(amount=Decimal("0.00"))
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_negative_raises_validation_error(self):
        op = self._make_op(amount=Decimal("-500.00"))
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Officer validation
    # ------------------------------------------------------------------

    def test_officer_user_must_be_staff(self):
        non_staff_user = User.objects.create_user(
            username="non_staff", password="testpass", is_staff=False
        )

        op = self._make_op(officer=non_staff_user)
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_must_be_active(self):
        self.officer_user.is_active = False
        self.officer_user.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------

    def test_source_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        other_project = _make_project_entity("Other Project")
        op.source = other_project
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        other_vendor = _make_vendor_entity("Other Vendor")
        _make_vendor_stakeholder(self.project_entity, other_vendor)
        op.destination = other_vendor
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        op.amount = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            op.save()


# ---------------------------------------------------------------------------
# PurchasePaymentTest
# ---------------------------------------------------------------------------


class PurchasePaymentTest(TestCase):
    """
    Tests for PURCHASE_PAYMENT transactions.

    The project records a purchase obligation on save (PURCHASE_ISSUANCE, non-cash).
    Payments are created explicitly and move funds: project.fund → vendor.fund.
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
        self.assertEqual(tx.source, self.project_entity.fund)
        self.assertEqual(tx.target, self.vendor_entity.fund)

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
        balance_before = self.project_entity.fund.balance

        self._pay(Decimal("600.00"))

        self.project_entity.fund.refresh_from_db()
        self.assertEqual(
            self.project_entity.fund.balance,
            balance_before - Decimal("600.00"),
        )

    def test_vendor_fund_increases_by_payment_amount(self):
        balance_before = self.vendor_entity.fund.balance

        self._pay(Decimal("600.00"))

        self.vendor_entity.fund.refresh_from_db()
        self.assertEqual(
            self.vendor_entity.fund.balance,
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
        balance_before_reversal = self.project_entity.fund.balance

        self.op.reverse(officer=self.officer_user)

        self.project_entity.fund.refresh_from_db()
        self.assertEqual(self.project_entity.fund.balance, balance_before_reversal)

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
