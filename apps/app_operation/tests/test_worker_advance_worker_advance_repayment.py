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


class WorkerAdvanceRepaymentTest(TestCase):
    """
    Tests for WORKER_ADVANCE_REPAYMENT transactions — worker returning the
    advance to the project fund.

    The worker's fund is already seeded by the advance (WORKER_ADVANCE_PAYMENT),
    so no additional injection is needed before repayments.
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

    def _repay(self, amount):
        self.op.create_repayment_transaction(
            amount=amount,
            officer=self.officer,
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

        tx = self.op.get_all_transactions().get(
            type=TransactionType.WORKER_ADVANCE_REPAYMENT
        )
        self.assertEqual(tx.source, self.worker_entity)
        self.assertEqual(tx.target, self.project_entity)

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
        balance_before = self.worker_entity.balance

        self._repay(Decimal("400.00"))

        self.assertEqual(self.worker_entity.balance, balance_before - Decimal("400.00"))

    def test_project_fund_increases_after_repayment(self):
        balance_before = self.project_entity.balance

        self._repay(Decimal("400.00"))

        self.assertEqual(
            self.project_entity.balance, balance_before + Decimal("400.00")
        )

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
