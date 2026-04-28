from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (

    CashInjectionOperation,
    CashWithdrawalOperation,
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()



class CashWithdrawalReversalTest(TestCase):
    def setUp(self):
        self.world_entity = Entity.create(EntityType.WORLD)
        self.officer_user = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )

        self.withdrawer_entity = Entity.create(
            EntityType.PERSON, name="Withdrawer Person"
        )

        # Fund the withdrawer so the withdrawal operation can be created
        CashInjectionOperation(
            source=self.world_entity,
            destination=self.withdrawer_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            description="Setup injection",
            officer=self.officer_user,
        ).save()

        self.op = CashWithdrawalOperation(
            source=self.withdrawer_entity,
            destination=self.world_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.CASH_WITHDRAWAL,
            date=date.today(),
            description="Test cash withdrawal",
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

    def test_reverse_creates_counter_transactions(self):
        reversal = self.op.reverse(officer=self.officer_user)

        original_txs = self.op.get_all_transactions()
        self.assertEqual(original_txs.count(), 4)  # 2 original + 2 counter-transactions

        reversal_txs = reversal.get_all_transactions()
        self.assertEqual(reversal_txs.count(), 0)  # reversal op owns no transactions

        reversed_txs = original_txs.filter(reversal_of__isnull=False)
        self.assertEqual(reversed_txs.count(), 2)

    def test_reverse_counter_transactions_flip_funds(self):
        self.op.reverse(officer=self.officer_user)

        original_txs = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        for tx in original_txs:
            counter = tx.reversed_by
            self.assertEqual(counter.source, tx.target)
            self.assertEqual(counter.target, tx.source)
            self.assertEqual(counter.amount, tx.amount)

    def test_reverse_counter_transactions_preserve_type(self):
        self.op.reverse(officer=self.officer_user)

        original_txs = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        for tx in original_txs:
            self.assertEqual(tx.reversed_by.type, tx.type)

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

    # ------------------------------------------------------------------
    # Balance restoration
    # ------------------------------------------------------------------

    def test_withdrawer_balance_restored_after_reversal(self):
        # setUp already saved the withdrawal, so balance is already reduced
        balance_after_withdrawal = self.withdrawer_entity.balance
        self.op.reverse(officer=self.officer_user)

        self.assertEqual(
            self.withdrawer_entity.balance,
            balance_after_withdrawal + self.op.amount,
        )
