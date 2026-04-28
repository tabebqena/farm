from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CashInjectionOperation,
    ProjectFundingOperation,
    ProjectRefundOperation,
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


def _make_officer(username="officer"):
    return User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def _make_project(name="Test Project"):
    return Entity.create(EntityType.PROJECT, name=name)


class ProjectRefundReversalTest(TestCase):
    def setUp(self):
        self.world_entity = Entity.create(EntityType.WORLD)
        self.officer = _make_officer()

        shareholder_person = Entity.create(
            EntityType.PERSON, name="Shareholder Person", is_shareholder=True
        )
        self.shareholder_entity = shareholder_person

        self.project_entity = _make_project()

        Stakeholder(
            parent=self.project_entity,
            target=self.shareholder_entity,
            role=StakeholderRole.SHAREHOLDER,
        ).save()

        # Fund shareholder → fund project → create the refund op to reverse
        CashInjectionOperation(
            source=self.world_entity,
            destination=self.shareholder_entity,
            amount=Decimal("2000.00"),
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            description="Setup injection",
            officer=self.officer,
        ).save()

        ProjectFundingOperation(
            source=self.shareholder_entity,
            destination=self.project_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PROJECT_FUNDING,
            date=date.today(),
            description="Setup funding",
            officer=self.officer,
        ).save()

        self.op = ProjectRefundOperation(
            source=self.project_entity,
            destination=self.shareholder_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PROJECT_REFUND,
            date=date.today(),
            description="Test project refund",
            officer=self.officer,
        )
        self.op.save()

    # ------------------------------------------------------------------
    # Happy path
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

    def test_reversal_is_reversal(self):
        reversal = self.op.reverse(officer=self.officer)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reverse_inherits_amount_source_destination(self):
        reversal = self.op.reverse(officer=self.officer)

        self.assertEqual(reversal.amount, self.op.amount)
        self.assertEqual(reversal.source, self.op.source)
        self.assertEqual(reversal.destination, self.op.destination)

    def test_reverse_creates_counter_transactions(self):
        reversal = self.op.reverse(officer=self.officer)

        original_txs = self.op.get_all_transactions()
        self.assertEqual(original_txs.count(), 4)  # 2 original + 2 counter

        reversal_txs = reversal.get_all_transactions()
        self.assertEqual(reversal_txs.count(), 0)

        reversed_txs = original_txs.filter(reversal_of__isnull=False)
        self.assertEqual(reversed_txs.count(), 2)

    def test_reverse_counter_transactions_flip_funds(self):
        self.op.reverse(officer=self.officer)

        original_txs = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        for tx in original_txs:
            counter = tx.reversed_by
            self.assertEqual(counter.source, tx.target)
            self.assertEqual(counter.target, tx.source)
            self.assertEqual(counter.amount, tx.amount)

    def test_reverse_counter_transactions_preserve_type(self):
        self.op.reverse(officer=self.officer)

        original_txs = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        for tx in original_txs:
            self.assertEqual(tx.reversed_by.type, tx.type)

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

    # ------------------------------------------------------------------
    # Balance restoration
    # ------------------------------------------------------------------

    def test_project_fund_restored_after_reversal(self):
        balance_after_refund = self.project_entity.balance
        self.op.reverse(officer=self.officer)

        self.assertEqual(
            self.project_entity.balance,
            balance_after_refund + self.op.amount,
        )

    def test_shareholder_fund_restored_after_reversal(self):
        balance_after_refund = self.shareholder_entity.balance
        self.op.reverse(officer=self.officer)

        self.assertEqual(
            self.shareholder_entity.balance,
            balance_after_refund - self.op.amount,
        )
