from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, Person, Project, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CapitalGainOperation,
    CashInjectionOperation,
    WorkerAdvanceOperation,
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username="officer"):
    user = User.objects.create_user(username=username, password="testpass", is_staff=True)
    person = Person.create(private_name=f"Officer {username}", auth_user=user)
    return person.entity


def _make_person_entity(name):
    person = Person.create(private_name=name)
    return person.entity


def _make_project_entity(name):
    project = Project(name=name)
    project.save()
    return Entity.create(owner=project)


def _inject_person(world_entity, dest_entity, amount, officer_entity):
    """Seed a Person entity's fund via CashInjection."""
    CashInjectionOperation(
        source=world_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CASH_INJECTION,
        date=date.today(),
        description="Seed balance",
        officer=officer_entity,
    ).save()


def _inject_project(system_entity, dest_entity, amount, officer_entity):
    """Seed a Project entity's fund via CapitalGain."""
    CapitalGainOperation(
        source=system_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=date.today(),
        description="Seed project balance",
        officer=officer_entity,
    ).save()


def _make_worker_stakeholder(project_entity, worker_entity, role=StakeholderRole.WORKER, active=True):
    sh = Stakeholder(parent=project_entity, target=worker_entity, role=role, active=active)
    sh.save()
    return sh


# ---------------------------------------------------------------------------
# WorkerAdvanceCreateTest
# ---------------------------------------------------------------------------


class WorkerAdvanceCreateTest(TestCase):
    """
    Tests for operation creation: validation, one-shot transactions, and fund balances.

    At creation the operation issues both WORKER_ADVANCE_ISSUANCE and
    WORKER_ADVANCE_PAYMENT in one atomic step (one-shot pattern).
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.officer_entity = _make_officer()

        self.project_entity = _make_project_entity("Test Farm Project")
        _inject_project(self.system_entity, self.project_entity, Decimal("5000.00"), self.officer_entity)

        self.worker_entity = _make_person_entity("Ali Worker")
        _make_worker_stakeholder(self.project_entity, self.worker_entity)

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.project_entity,
            destination=self.worker_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.WORKER_ADVANCE,
            date=date.today(),
            description="Test worker advance",
            officer=self.officer_entity,
        )
        defaults.update(kwargs)
        return WorkerAdvanceOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path — one-shot transaction creation
    # ------------------------------------------------------------------

    def test_creates_both_issuance_and_payment_transactions_at_creation(self):
        op = self._make_op()
        op.save()

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 2)
        self.assertTrue(
            transactions.filter(type=TransactionType.WORKER_ADVANCE_ISSUANCE).exists(),
            "Issuance transaction must be created",
        )
        self.assertTrue(
            transactions.filter(type=TransactionType.WORKER_ADVANCE_PAYMENT).exists(),
            "Payment transaction must be created",
        )

    def test_issuance_transaction_direction_is_project_to_worker(self):
        op = self._make_op()
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.WORKER_ADVANCE_ISSUANCE)
        self.assertEqual(tx.source, self.project_entity.fund)
        self.assertEqual(tx.target, self.worker_entity.fund)

    def test_payment_transaction_direction_is_project_to_worker(self):
        op = self._make_op()
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.WORKER_ADVANCE_PAYMENT)
        self.assertEqual(tx.source, self.project_entity.fund)
        self.assertEqual(tx.target, self.worker_entity.fund)

    def test_both_transactions_amount_match_operation(self):
        op = self._make_op(amount=Decimal("800.00"))
        op.save()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.amount, Decimal("800.00"))

    def test_project_fund_decreases_by_advance_amount(self):
        balance_before = self.project_entity.fund.balance

        op = self._make_op(amount=Decimal("600.00"))
        op.save()

        self.assertEqual(
            self.project_entity.fund.balance,
            balance_before - Decimal("600.00"),
        )

    def test_worker_fund_increases_by_advance_amount(self):
        balance_before = self.worker_entity.fund.balance

        op = self._make_op(amount=Decimal("600.00"))
        op.save()

        self.assertEqual(
            self.worker_entity.fund.balance,
            balance_before + Decimal("600.00"),
        )

    def test_amount_remaining_to_repay_equals_full_amount_after_creation(self):
        op = self._make_op(amount=Decimal("1000.00"))
        op.save()

        self.assertEqual(op.amount_remaining_to_repay, Decimal("1000.00"))

    # ------------------------------------------------------------------
    # One-shot constraint
    # ------------------------------------------------------------------

    def test_one_shot_prevents_additional_payment_transaction(self):
        op = self._make_op()
        op.save()

        with self.assertRaises(ValidationError):
            op.create_payment_transaction(
                amount=op.amount,
                officer=self.officer_entity,
                date=date.today(),
            )

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

    def test_source_fund_insufficient_balance_raises_validation_error(self):
        op = self._make_op(amount=Decimal("99999.00"))
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation
    # ------------------------------------------------------------------

    def test_destination_must_be_a_person_entity(self):
        # clean_destination checks destination.person first, before any stakeholder check
        other_project = _make_project_entity("Other Project")
        op = self._make_op(destination=other_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_active(self):
        self.worker_entity.active = False
        self.worker_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_without_stakeholder_relationship_raises_validation_error(self):
        unrelated_person = _make_person_entity("Unrelated Person")
        op = self._make_op(destination=unrelated_person)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_with_inactive_stakeholder_raises_validation_error(self):
        another_worker = _make_person_entity("Inactive Worker")
        _make_worker_stakeholder(self.project_entity, another_worker, active=False)

        op = self._make_op(destination=another_worker)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_worker_role_stakeholder(self):
        """A person with a non-WORKER stakeholder role should not be a valid destination."""
        non_worker = _make_person_entity("Client Person")
        _make_worker_stakeholder(self.project_entity, non_worker, role=StakeholderRole.CLIENT)

        op = self._make_op(destination=non_worker)
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

    def test_officer_must_be_a_person_entity(self):
        op = self._make_op(officer=self.system_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_must_have_auth_user(self):
        no_user_person = Person.create(private_name="No User Officer")
        op = self._make_op(officer=no_user_person.entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_user_must_be_staff(self):
        non_staff_user = User.objects.create_user(
            username="non_staff", password="testpass", is_staff=False
        )
        non_staff_person = Person.create(
            private_name="Non Staff Officer", auth_user=non_staff_user
        )
        op = self._make_op(officer=non_staff_person.entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_must_be_active(self):
        self.officer_entity.active = False
        self.officer_entity.save()

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

        other_worker = _make_person_entity("Other Worker")
        _make_worker_stakeholder(self.project_entity, other_worker)
        op.destination = other_worker
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        op.amount = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # check_balance_on_payment
    # ------------------------------------------------------------------

    def test_check_balance_on_payment_is_disabled(self):
        """Balance is enforced by clean() at creation; no per-payment gate needed."""
        self.assertFalse(WorkerAdvanceOperation.check_balance_on_payment)


# ---------------------------------------------------------------------------
# WorkerAdvanceRepaymentTest
# ---------------------------------------------------------------------------


class WorkerAdvanceRepaymentTest(TestCase):
    """
    Tests for WORKER_ADVANCE_REPAYMENT transactions — worker returning the
    advance to the project fund.

    The worker's fund is already seeded by the advance (WORKER_ADVANCE_PAYMENT),
    so no additional injection is needed before repayments.
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.officer_entity = _make_officer()

        self.project_entity = _make_project_entity("Farm Project")
        _inject_project(self.system_entity, self.project_entity, Decimal("5000.00"), self.officer_entity)

        self.worker_entity = _make_person_entity("Ali Worker")
        _make_worker_stakeholder(self.project_entity, self.worker_entity)

        self.op = WorkerAdvanceOperation(
            source=self.project_entity,
            destination=self.worker_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.WORKER_ADVANCE,
            date=date.today(),
            description="Test worker advance",
            officer=self.officer_entity,
        )
        self.op.save()

    def _repay(self, amount):
        self.op.create_repayment_transaction(
            amount=amount,
            officer=self.officer_entity,
            date=date.today(),
        )

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_repayment_creates_repayment_transaction(self):
        self._repay(Decimal("400.00"))

        repayment_txs = self.op.get_all_transactions().filter(
            type=TransactionType.WORKER_ADVANCE_REPAYMENT
        )
        self.assertEqual(repayment_txs.count(), 1)

    def test_repayment_transaction_direction_is_worker_to_project(self):
        self._repay(Decimal("400.00"))

        tx = self.op.get_all_transactions().get(type=TransactionType.WORKER_ADVANCE_REPAYMENT)
        self.assertEqual(tx.source, self.worker_entity.fund)
        self.assertEqual(tx.target, self.project_entity.fund)

    def test_amount_remaining_to_repay_decreases_after_repayment(self):
        self._repay(Decimal("400.00"))

        self.assertEqual(self.op.amount_remaining_to_repay, Decimal("600.00"))

    def test_multiple_partial_repayments_accumulate(self):
        self._repay(Decimal("300.00"))
        self._repay(Decimal("300.00"))

        self.assertEqual(self.op.amount_remaining_to_repay, Decimal("400.00"))

    def test_full_repayment_marks_as_fully_repayed(self):
        self._repay(Decimal("1000.00"))

        self.assertTrue(self.op.is_fully_repayed)
        self.assertEqual(self.op.amount_remaining_to_repay, Decimal("0.00"))

    def test_worker_fund_decreases_after_repayment(self):
        balance_before = self.worker_entity.fund.balance

        self._repay(Decimal("400.00"))

        self.assertEqual(self.worker_entity.fund.balance, balance_before - Decimal("400.00"))

    def test_project_fund_increases_after_repayment(self):
        balance_before = self.project_entity.fund.balance

        self._repay(Decimal("400.00"))

        self.assertEqual(self.project_entity.fund.balance, balance_before + Decimal("400.00"))

    # ------------------------------------------------------------------
    # Over-repayment blocked
    # ------------------------------------------------------------------

    def test_repayment_exceeding_advance_amount_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._repay(Decimal("1500.00"))

    def test_partial_repayment_then_over_repayment_raises_validation_error(self):
        self._repay(Decimal("800.00"))

        with self.assertRaises(ValidationError):
            self._repay(Decimal("300.00"))  # only 200 remaining

    def test_zero_repayment_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._repay(Decimal("0.00"))


# ---------------------------------------------------------------------------
# WorkerAdvanceReversalTest
# ---------------------------------------------------------------------------


class WorkerAdvanceReversalTest(TestCase):
    """
    Tests for operation reversal.

    Reversal is only allowed when no repayments exist. Both the issuance and
    payment transactions are implicitly reversed (counter-transactions created
    automatically).
    """

    def setUp(self):
        self.system_entity = Entity.create(is_system=True)
        self.officer_entity = _make_officer()

        self.project_entity = _make_project_entity("Farm Project")
        _inject_project(self.system_entity, self.project_entity, Decimal("5000.00"), self.officer_entity)

        self.worker_entity = _make_person_entity("Ali Worker")
        _make_worker_stakeholder(self.project_entity, self.worker_entity)

        self.op = WorkerAdvanceOperation(
            source=self.project_entity,
            destination=self.worker_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.WORKER_ADVANCE,
            date=date.today(),
            description="Test worker advance",
            officer=self.officer_entity,
        )
        self.op.save()

    # ------------------------------------------------------------------
    # Happy path — no repayments, reversal is allowed
    # ------------------------------------------------------------------

    def test_reverse_creates_reversal_operation(self):
        reversal = self.op.reverse(officer=self.officer_entity)

        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, self.op)

    def test_reverse_marks_original_as_reversed(self):
        reversal = self.op.reverse(officer=self.officer_entity)

        self.op.refresh_from_db()
        self.assertTrue(self.op.is_reversed)
        self.assertEqual(self.op.reversed_by, reversal)

    def test_reversal_is_marked_as_reversal(self):
        reversal = self.op.reverse(officer=self.officer_entity)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reverse_inherits_amount_source_destination(self):
        reversal = self.op.reverse(officer=self.officer_entity)

        self.assertEqual(reversal.amount, self.op.amount)
        self.assertEqual(reversal.source, self.op.source)
        self.assertEqual(reversal.destination, self.op.destination)

    def test_reverse_creates_counter_transactions_for_both_issuance_and_payment(self):
        self.op.reverse(officer=self.officer_entity)

        all_txs = self.op.get_all_transactions()
        # 2 original (issuance + payment) + 2 counter-transactions
        self.assertEqual(all_txs.count(), 4)

        counter_txs = all_txs.filter(reversal_of__isnull=False)
        self.assertEqual(counter_txs.count(), 2)

    def test_reverse_counter_transactions_flip_funds(self):
        self.op.reverse(officer=self.officer_entity)

        original_txs = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        for tx in original_txs:
            counter = tx.reversed_by
            self.assertEqual(counter.source, tx.target)
            self.assertEqual(counter.target, tx.source)
            self.assertEqual(counter.amount, tx.amount)

    def test_project_fund_restored_after_reversal(self):
        balance_after_advance = self.project_entity.fund.balance
        self.op.reverse(officer=self.officer_entity)

        self.assertEqual(
            self.project_entity.fund.balance,
            balance_after_advance + self.op.amount,
        )

    def test_worker_fund_restored_after_reversal(self):
        balance_after_advance = self.worker_entity.fund.balance
        self.op.reverse(officer=self.officer_entity)

        self.assertEqual(
            self.worker_entity.fund.balance,
            balance_after_advance - self.op.amount,
        )

    # ------------------------------------------------------------------
    # Reversal blocked by outstanding repayments
    # ------------------------------------------------------------------

    def test_reversal_blocked_when_repayment_exists(self):
        self.op.create_repayment_transaction(
            amount=Decimal("500.00"),
            officer=self.officer_entity,
            date=date.today(),
        )

        with self.assertRaises(ValidationError):
            self.op.reverse(officer=self.officer_entity)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    def test_cannot_reverse_already_reversed_operation(self):
        self.op.reverse(officer=self.officer_entity)
        self.op.refresh_from_db()

        with self.assertRaises(ValidationError):
            self.op.reverse(officer=self.officer_entity)

    def test_cannot_reverse_a_reversal(self):
        reversal = self.op.reverse(officer=self.officer_entity)

        with self.assertRaises(ValidationError):
            reversal.reverse(officer=self.officer_entity)
