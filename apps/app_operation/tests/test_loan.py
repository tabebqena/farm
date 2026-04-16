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
        self.assertEqual(tx.source, self.creditor_entity.fund)
        self.assertEqual(tx.target, self.debtor_entity.fund)

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
        self.creditor_entity.fund.active = False
        self.creditor_entity.fund.save()

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
        self.assertEqual(tx.source, self.creditor_entity.fund)
        self.assertEqual(tx.target, self.debtor_entity.fund)

    def test_creditor_fund_decreases_after_payment(self):
        balance_before = self.creditor_entity.fund.balance

        self.op.create_payment_transaction(
            amount=Decimal("600.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        self.assertEqual(
            self.creditor_entity.fund.balance, balance_before - Decimal("600.00")
        )

    def test_debtor_fund_increases_after_payment(self):
        balance_before = self.debtor_entity.fund.balance

        self.op.create_payment_transaction(
            amount=Decimal("600.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        self.assertEqual(
            self.debtor_entity.fund.balance, balance_before + Decimal("600.00")
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
        self.assertEqual(tx.source, self.debtor_entity.fund)
        self.assertEqual(tx.target, self.creditor_entity.fund)

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
        balance_before = self.debtor_entity.fund.balance

        self.op.create_repayment_transaction(
            amount=Decimal("400.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        self.assertEqual(
            self.debtor_entity.fund.balance, balance_before - Decimal("400.00")
        )

    def test_creditor_fund_increases_after_repayment(self):
        balance_before = self.creditor_entity.fund.balance

        self.op.create_repayment_transaction(
            amount=Decimal("400.00"),
            officer=self.officer_user,
            date=date.today(),
        )

        self.assertEqual(
            self.creditor_entity.fund.balance, balance_before + Decimal("400.00")
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
