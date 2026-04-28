from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CashInjectionOperation, LoanOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


def _make_officer(username="officer"):
    return User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def _make_person_entity(name):
    person = Entity.create(EntityType.PERSON, name=name)
    return person


def _make_project_entity(name):
    return Entity.create(EntityType.PROJECT, name=name)


def _inject(world_entity, dest_entity, amount, officer_user):
    """Seed a Person entity's fund via CashInjection."""
    CashInjectionOperation(
        source=world_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CASH_INJECTION,
        date=date.today(),
        description="Seed balance",
        officer=officer_user,
    ).save()


class LoanRepaymentTest(TestCase):
    """
    Tests for LOAN_REPAYMENT transactions — debtor returning funds to creditor.
    Uses Person entities for both parties so CashInjection can seed both funds.
    """

    def setUp(self):
        self.world_entity = Entity.create(EntityType.WORLD)
        self.officer_user = _make_officer()
        self.creditor_entity = _make_person_entity("Creditor Person")
        self.debtor_entity = _make_person_entity("Debtor Person")

        _inject(
            self.world_entity,
            self.creditor_entity,
            Decimal("5000.00"),
            self.officer_user,
        )
        # Seed debtor fund so it has funds to repay with
        _inject(
            self.world_entity,
            self.debtor_entity,
            Decimal("2000.00"),
            self.officer_user,
        )

        self.op = LoanOperation(
            source=self.creditor_entity,
            destination=self.debtor_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.LOAN,
            date=date.today(),
            description="Test loan",
            officer=self.officer_user,
        )
        self.op.save()

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_repayment_creates_loan_repayment_transaction(self):
        self.op.create_repayment_transaction(
            amount=Decimal("400.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        repayment_txs = self.op.get_all_transactions().filter(
            type=TransactionType.LOAN_REPAYMENT
        )
        self.assertEqual(repayment_txs.count(), 1)

    def test_repayment_transaction_direction_is_debtor_to_creditor(self):
        self.op.create_repayment_transaction(
            amount=Decimal("400.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        tx = self.op.get_all_transactions().get(type=TransactionType.LOAN_REPAYMENT)
        self.assertEqual(tx.source, self.debtor_entity)
        self.assertEqual(tx.target, self.creditor_entity)

    def test_amount_remaining_to_repay_decreases_after_repayment(self):
        self.op.create_repayment_transaction(
            amount=Decimal("400.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        self.assertEqual(self.op.amount_remaining_to_repay, Decimal("600.00"))

    def test_multiple_repayments_accumulate(self):
        self.op.create_repayment_transaction(
            amount=Decimal("300.00"),
            officer=self.officer_user,
            date=date.today(),
        )
        self.op.create_repayment_transaction(
            amount=Decimal("300.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        self.assertEqual(self.op.amount_remaining_to_repay, Decimal("400.00"))

    def test_full_repayment_marks_as_fully_repayed(self):
        self.op.create_repayment_transaction(
            amount=Decimal("1000.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        self.assertTrue(self.op.is_fully_repayed)
        self.assertEqual(self.op.amount_remaining_to_repay, Decimal("0.00"))

    def test_debtor_fund_decreases_after_repayment(self):
        balance_before = self.debtor_entity.balance

        self.op.create_repayment_transaction(
            amount=Decimal("400.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        self.assertEqual(
            self.debtor_entity.balance, balance_before - Decimal("400.00")
        )

    def test_creditor_fund_increases_after_repayment(self):
        balance_before = self.creditor_entity.balance

        self.op.create_repayment_transaction(
            amount=Decimal("400.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        self.assertEqual(
            self.creditor_entity.balance, balance_before + Decimal("400.00")
        )

    # ------------------------------------------------------------------
    # Over-repayment blocked
    # ------------------------------------------------------------------

    def test_repayment_exceeding_remaining_balance_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self.op.create_repayment_transaction(
                amount=Decimal("1500.00"),  # exceeds 1000 issuance
                officer=self.officer_user,
                date=date.today(),
            )

    def test_partial_repayment_then_over_repayment_raises_validation_error(self):
        self.op.create_repayment_transaction(
            amount=Decimal("800.00"),
            officer=self.officer_user,
            date=date.today(),
        )
        with self.assertRaises(ValidationError):
            self.op.create_repayment_transaction(
                amount=Decimal("300.00"),  # only 200 remaining
                officer=self.officer_user,
                date=date.today(),
            )

    def test_zero_repayment_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self.op.create_repayment_transaction(
                amount=Decimal("0.00"),
                officer=self.officer_user,
                date=date.today(),
            )
