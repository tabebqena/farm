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


class LoanDisbursementTest(TestCase):
    """
    Tests for LOAN_PAYMENT (disbursement) transactions, which represent
    additional fund transfers from creditor to debtor after the issuance.
    These are the only transactions that affect fund balances for a loan.
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

    def test_payment_creates_loan_payment_transaction(self):
        self.op.create_payment_transaction(
            amount=Decimal("500.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        payment_txs = self.op.get_all_transactions().filter(
            type=TransactionType.LOAN_PAYMENT
        )
        self.assertEqual(payment_txs.count(), 1)

    def test_payment_transaction_direction_is_creditor_to_debtor(self):
        self.op.create_payment_transaction(
            amount=Decimal("500.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        tx = self.op.get_all_transactions().get(type=TransactionType.LOAN_PAYMENT)
        self.assertEqual(tx.source, self.creditor_entity)
        self.assertEqual(tx.target, self.debtor_entity)

    def test_creditor_fund_decreases_after_payment(self):
        balance_before = self.creditor_entity.balance

        self.op.create_payment_transaction(
            amount=Decimal("600.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        self.assertEqual(
            self.creditor_entity.balance, balance_before - Decimal("600.00")
        )

    def test_debtor_fund_increases_after_payment(self):
        balance_before = self.debtor_entity.balance

        self.op.create_payment_transaction(
            amount=Decimal("600.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        self.assertEqual(
            self.debtor_entity.balance, balance_before + Decimal("600.00")
        )

    def test_multiple_payment_disbursements_allowed(self):
        self.op.create_payment_transaction(
            amount=Decimal("300.00"),
            officer=self.officer_user,
            date=date.today(),
        )
        self.op.create_payment_transaction(
            amount=Decimal("200.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        payment_txs = self.op.get_all_transactions().filter(
            type=TransactionType.LOAN_PAYMENT
        )
        self.assertEqual(payment_txs.count(), 2)
