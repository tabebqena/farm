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



class LoanReversalTest(TestCase):
    def setUp(self):
        self.world_entity = Entity.create(EntityType.WORLD)
        self.officer_user = _make_officer()
        self.creditor_entity = _make_person_entity("Creditor Person")
        self.debtor_entity = _make_project_entity("Debtor Project")

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

    # ------------------------------------------------------------------
    # Happy path (no LOAN_PAYMENT disbursements to clear)
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

    def test_reverse_creates_counter_issuance_transaction(self):
        self.op.reverse(officer=self.officer_user)

        all_txs = self.op.get_all_transactions()
        reversed_txs = all_txs.filter(reversal_of__isnull=False)
        self.assertEqual(reversed_txs.count(), 1)
        self.assertEqual(reversed_txs.first().type, TransactionType.LOAN_ISSUANCE)

    def test_reverse_counter_transaction_flips_funds(self):
        self.op.reverse(officer=self.officer_user)

        original_tx = self.op.get_all_transactions().get(
            type=TransactionType.LOAN_ISSUANCE, reversal_of__isnull=True
        )
        counter = original_tx.reversed_by
        self.assertEqual(counter.source, original_tx.target)
        self.assertEqual(counter.target, original_tx.source)
        self.assertEqual(counter.amount, original_tx.amount)

    # ------------------------------------------------------------------
    # Reversal blocked by outstanding LOAN_PAYMENT disbursements
    # ------------------------------------------------------------------

    def test_reversal_blocked_when_payment_disbursement_exists(self):
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
