from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CapitalGainOperation,
    CorrectionCreditOperation,
    CorrectionDebitOperation,
)
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer():
    return User.objects.create_user(
        username="officer", password="testpass", is_staff=True
    )


def _make_project_entity(name="Test Project"):
    return Entity.create(EntityType.PROJECT, name=name)


def _seed_balance(system_entity, project_entity, officer_user, amount):
    """Give a project fund some balance via a CapitalGain."""
    op = CapitalGainOperation(
        source=system_entity,
        destination=project_entity,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=date.today(),
        description="Seed balance",
        officer=officer_user,
    )
    op.save()


# ===========================================================================
# Correction Credit — Create
# ===========================================================================


class CorrectionDebitCreateTest(TestCase):
    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = _make_officer()
        self.project_entity = _make_project_entity()

        # Seed project fund so debit operations can succeed
        _seed_balance(
            self.system_entity,
            self.project_entity,
            self.officer_user,
            Decimal("2000.00"),
        )

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.project_entity,
            destination=self.system_entity,
            amount=Decimal("500.00"),
            operation_type=OperationType.CORRECTION_DEBIT,
            date=date.today(),
            description="Test correction debit",
            officer=self.officer_user,
        )
        defaults.update(kwargs)
        return CorrectionDebitOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_creates_issuance_and_payment_transactions(self):
        op = self._make_op()
        op.save()

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 2)
        self.assertTrue(
            transactions.filter(type=TransactionType.CORRECTION_DEBIT_ISSUANCE).exists()
        )
        self.assertTrue(
            transactions.filter(type=TransactionType.CORRECTION_DEBIT_PAYMENT).exists()
        )

    def test_transaction_funds_are_correct(self):
        op = self._make_op()
        op.save()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.source, self.project_entity)
            self.assertEqual(tx.target, self.system_entity)

    def test_is_fully_settled_after_creation(self):
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        self.assertEqual(op.amount_settled, Decimal("500.00"))
        self.assertTrue(op.is_fully_settled)
        self.assertEqual(op.amount_remaining_to_settle, Decimal("0.00"))

    def test_project_fund_decreases_by_correction_amount(self):
        self.project_entity.refresh_from_db()
        balance_before = self.project_entity.balance

        op = self._make_op(amount=Decimal("300.00"))
        op.save()

        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            balance_before - Decimal("300.00"),
        )

    def test_no_category_config(self):
        self.assertFalse(CorrectionDebitOperation.has_category)
        self.assertFalse(CorrectionDebitOperation.category_required)

    # ------------------------------------------------------------------
    # Source validation
    # ------------------------------------------------------------------

    def test_source_must_be_project_entity(self):
        person = Entity.create(EntityType.PERSON, name="Some Person")
        op = self._make_op(source=person)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_system_entity_raises_validation_error(self):
        op = self._make_op(source=self.system_entity, destination=self.system_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_must_be_active(self):
        self.project_entity.active = False
        self.project_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_fund_must_be_active(self):
        self.project_entity.active = False
        self.project_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation
    # ------------------------------------------------------------------

    def test_destination_must_be_system_entity(self):
        non_system = Entity.create(EntityType.PERSON, name="Non System Person")
        op = self._make_op(destination=non_system)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_world_entity_raises_validation_error(self):
        world_entity = Entity.create(EntityType.WORLD)
        op = self._make_op(destination=world_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_active(self):
        self.system_entity.active = False
        self.system_entity.save()

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
        op = self._make_op(amount=Decimal("-100.00"))
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

        other_entity = _make_project_entity("Other Project")
        _seed_balance(
            self.system_entity, other_entity, self.officer_user, Decimal("1000.00")
        )
        op.source = other_entity
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable(self):
        op = self._make_op()
        op.save()

        other_entity = _make_project_entity("Other Project 2")
        op.destination = other_entity
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

    def test_check_balance_on_payment_is_disabled(self):
        """Corrections bypass balance checks; admins need this to fix ledger errors."""
        self.assertFalse(CorrectionDebitOperation.check_balance_on_payment)

    def test_debit_succeeds_even_with_insufficient_balance(self):
        """A debit for more than the fund balance must succeed — no balance gate."""
        self.project_entity.refresh_from_db()
        over_amount = self.project_entity.balance + Decimal("9999.00")
        op = self._make_op(amount=over_amount)
        op.save()
        self.assertIsNotNone(op.pk)

    # ------------------------------------------------------------------
    # One-shot / can_pay constraint
    # ------------------------------------------------------------------

    def test_can_pay_is_false(self):
        self.assertFalse(CorrectionDebitOperation.can_pay)

    def test_one_shot_prevents_second_payment(self):
        op = self._make_op()
        op.save()

        with self.assertRaises(ValidationError):
            op.create_payment_transaction(
                amount=op.amount,
                officer=self.officer_user,
                date=date.today(),
            )


# ===========================================================================
# Correction Debit — Reversal
# ===========================================================================
