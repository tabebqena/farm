from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
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
    return User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def _make_person_entity(name, is_worker=False):
    return Entity.create(EntityType.PERSON, name=name, is_worker=is_worker)


def _make_client_entity(name, is_client=False):
    return Entity.create(EntityType.CLIENT, name=name, is_client=is_client)


def _make_vendor_entity(name):
    return Entity.create(EntityType.VENDOR, name)


def _make_project_entity(name):
    return Entity.create(EntityType.PROJECT, name)


def _inject_person(world_entity, dest_entity, amount, officer):
    """Seed a Person entity's fund via CashInjection."""
    CashInjectionOperation(
        source=world_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CASH_INJECTION,
        date=date.today(),
        description="Seed balance",
        officer=officer,
    ).save()


def _inject_project(system_entity, dest_entity, amount, officer):
    """Seed a Project entity's fund via CapitalGain."""
    CapitalGainOperation(
        source=system_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=date.today(),
        description="Seed project balance",
        officer=officer,
    ).save()


def _make_worker_stakeholder(
    project_entity, worker_entity, role=StakeholderRole.WORKER, active=True
):
    sh = Stakeholder(
        parent=project_entity, target=worker_entity, role=role, active=active
    )
    sh.save()
    return sh


# ---------------------------------------------------------------------------
# WorkerAdvanceCreateTest
# ---------------------------------------------------------------------------



class WorkerAdvanceReversalTest(TestCase):
    """
    Tests for operation reversal.

    Reversal is only allowed when no repayments exist. Both the issuance and
    payment transactions are implicitly reversed (counter-transactions created
    automatically).
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer = _make_officer()

        self.project_entity = _make_project_entity("Farm Project")
        _inject_project(
            self.system_entity, self.project_entity, Decimal("5000.00"), self.officer
        )

        self.worker_entity = _make_person_entity("Ali Worker", is_worker=True)
        _make_worker_stakeholder(self.project_entity, self.worker_entity)

        self.op = WorkerAdvanceOperation(
            source=self.project_entity,
            destination=self.worker_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.WORKER_ADVANCE,
            date=date.today(),
            description="Test worker advance",
            officer=self.officer,
        )
        self.op.save()

    # ------------------------------------------------------------------
    # Happy path — no repayments, reversal is allowed
    # ------------------------------------------------------------------

    def test_reverse_creates_reversal_operation(self):
        reversal = self.op.reverse(officer=self.officer)

        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, self.op)

    def test_reverse_marks_original_as_reversed(self):
        reversal = self.op.reverse(officer=self.officer)

        self.op.refresh_from_db()
        self.assertTrue(self.op.is_reversed)
        self.assertEqual(self.op.reversed_by, reversal)

    def test_reversal_is_marked_as_reversal(self):
        reversal = self.op.reverse(officer=self.officer)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reverse_inherits_amount_source_destination(self):
        reversal = self.op.reverse(officer=self.officer)

        self.assertEqual(reversal.amount, self.op.amount)
        self.assertEqual(reversal.source, self.op.source)
        self.assertEqual(reversal.destination, self.op.destination)

    def test_reverse_creates_counter_transactions_for_both_issuance_and_payment(self):
        self.op.reverse(officer=self.officer)

        all_txs = self.op.get_all_transactions()
        # 2 original (issuance + payment) + 2 counter-transactions
        self.assertEqual(all_txs.count(), 4)

        counter_txs = all_txs.filter(reversal_of__isnull=False)
        self.assertEqual(counter_txs.count(), 2)

    def test_reverse_counter_transactions_flip_funds(self):
        self.op.reverse(officer=self.officer)

        original_txs = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        for tx in original_txs:
            counter = tx.reversed_by
            self.assertEqual(counter.source, tx.target)
            self.assertEqual(counter.target, tx.source)
            self.assertEqual(counter.amount, tx.amount)

    def test_project_fund_restored_after_reversal(self):
        balance_after_advance = self.project_entity.balance
        self.op.reverse(officer=self.officer)

        self.assertEqual(
            self.project_entity.balance,
            balance_after_advance + self.op.amount,
        )

    def test_worker_fund_restored_after_reversal(self):
        balance_after_advance = self.worker_entity.balance
        self.op.reverse(officer=self.officer)

        self.assertEqual(
            self.worker_entity.balance,
            balance_after_advance - self.op.amount,
        )

    # ------------------------------------------------------------------
    # Reversal blocked by outstanding repayments
    # ------------------------------------------------------------------

    def test_reversal_blocked_when_repayment_exists(self):
        self.op.create_repayment_transaction(
            amount=Decimal("500.00"),
            officer=self.officer,
            date=date.today(),
        )

        with self.assertRaises(ValidationError):
            self.op.reverse(officer=self.officer)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    def test_cannot_reverse_already_reversed_operation(self):
        self.op.reverse(officer=self.officer)
        self.op.refresh_from_db()

        with self.assertRaises(ValidationError):
            self.op.reverse(officer=self.officer)

    def test_cannot_reverse_a_reversal(self):
        reversal = self.op.reverse(officer=self.officer)

        with self.assertRaises(ValidationError):
            reversal.reverse(officer=self.officer)
