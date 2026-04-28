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


class LoanCreateTest(TestCase):
    """
    Tests for the issuance phase of a Loan operation.

    Note: LOAN_ISSUANCE is an issuance-type transaction (not a payment type),
    so it does NOT affect fund balances. Fund balance changes only occur via
    LOAN_PAYMENT (disbursements) and LOAN_REPAYMENT transactions.
    """

    def setUp(self):
        self.world_entity = Entity.create(EntityType.WORLD)
        self.officer_user = _make_officer()
        # Creditor: a Person entity seeded with funds
        self.creditor_entity = _make_person_entity("Creditor Person")
        _inject(
            self.world_entity,
            self.creditor_entity,
            Decimal("5000.00"),
            self.officer_user,
        )
        # Debtor: a Project entity (no seed needed — issuance doesn't check debtor balance)
        self.debtor_entity = _make_project_entity("Debtor Project")

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.creditor_entity,
            destination=self.debtor_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.LOAN,
            date=date.today(),
            description="Test loan",
            officer=self.officer_user,
        )
        defaults.update(kwargs)
        return LoanOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_creates_issuance_transaction_on_save(self):
        op = self._make_op()
        op.save()

        self.assertIsNotNone(op.pk)
        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 1)
        self.assertTrue(
            transactions.filter(type=TransactionType.LOAN_ISSUANCE).exists()
        )

    def test_issuance_transaction_direction_is_creditor_to_debtor(self):
        op = self._make_op()
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.LOAN_ISSUANCE)
        self.assertEqual(tx.source, self.creditor_entity)
        self.assertEqual(tx.target, self.debtor_entity)

    def test_issuance_transaction_amount_matches_operation(self):
        op = self._make_op(amount=Decimal("750.00"))
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.LOAN_ISSUANCE)
        self.assertEqual(tx.amount, Decimal("750.00"))

    def test_amount_remaining_to_repay_equals_issuance_amount_initially(self):
        op = self._make_op(amount=Decimal("1000.00"))
        op.save()

        self.assertEqual(op.amount_remaining_to_repay, Decimal("1000.00"))

    def test_creditor_property(self):
        op = self._make_op()
        op.save()

        self.assertEqual(op.creditor, self.creditor_entity)

    def test_debtor_property(self):
        op = self._make_op()
        op.save()

        self.assertEqual(op.debtor, self.debtor_entity)

    def test_project_as_creditor_person_as_debtor(self):
        project_creditor = _make_project_entity("Creditor Project")
        person_debtor = _make_person_entity("Debtor Person")

        op = self._make_op(source=project_creditor, destination=person_debtor)
        op.save()

        self.assertIsNotNone(op.pk)

    # ------------------------------------------------------------------
    # Source (creditor) validation
    # ------------------------------------------------------------------

    def test_source_must_be_active(self):
        self.creditor_entity.active = False
        self.creditor_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_fund_must_be_active(self):
        self.creditor_entity.active = False
        self.creditor_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination (debtor) validation
    # ------------------------------------------------------------------

    def test_destination_must_be_active(self):
        self.debtor_entity.active = False
        self.debtor_entity.save()

        op = self._make_op()
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

    def test_source_is_immutable(self):
        op = self._make_op()
        op.save()

        other_creditor = _make_person_entity("Other Creditor")
        op.source = other_creditor
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable(self):
        op = self._make_op()
        op.save()

        other_debtor = _make_project_entity("Other Debtor")
        op.destination = other_debtor
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_is_immutable(self):
        op = self._make_op()
        op.save()

        op.amount = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # check_balance_on_payment
    # ------------------------------------------------------------------

    def test_check_balance_on_payment_is_enabled(self):
        """Creditor fund balance is checked before each disbursement."""
        self.assertTrue(LoanOperation.check_balance_on_payment)
