from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_entity.models.category import FinancialCategory
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalGainOperation, ExpenseOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username="officer"):
    return User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def _make_person_entity(name):
    person = Entity.create(EntityType.PERSON, name=name)
    return person


def _make_project_entity(name):
    project = Entity.create(EntityType.PROJECT, name=name)
    project.save()
    return project


def _make_world_entity():
    return Entity.create(EntityType.WORLD)


def _inject_project(system_entity, dest_entity, amount, officer_user):
    """Seed a Project entity's fund via CapitalGain."""
    CapitalGainOperation(
        source=system_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=date.today(),
        description="Seed project balance",
        officer=officer_user,
    ).save()


def _make_expense_category(parent_entity, name="Veterinary Consultation"):
    from apps.app_operation.models import FinancialCategoriesEntitiesRelations

    cat, _ = FinancialCategory.objects.get_or_create(
        name=name,
        defaults={"category_type": "EXPENSE", "is_active": True},
    )
    FinancialCategoriesEntitiesRelations.objects.get_or_create(
        entity=parent_entity, category=cat, defaults={"max_limit": Decimal("0.00")}
    )
    return cat


# ---------------------------------------------------------------------------
# ExpenseCreateTest
# ---------------------------------------------------------------------------


class ExpenseReversalTest(TestCase):
    """
    Tests for expense operation reversal.

    Reversal is allowed only when no EXPENSE_PAYMENT transactions exist.
    Reversing the operation creates counter-transactions for the issuance.
    Since EXPENSE_ISSUANCE is non-cash, the project fund balance is unaffected
    both before and after reversal.
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.world_entity = _make_world_entity()
        self.officer_user = _make_officer()

        self.project_entity = _make_project_entity("Farm Project")
        _inject_project(
            self.system_entity,
            self.project_entity,
            Decimal("5000.00"),
            self.officer_user,
        )

        self.op = ExpenseOperation(
            source=self.project_entity,
            destination=self.world_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.EXPENSE,
            date=date.today(),
            description="Test expense",
            officer=self.officer_user,
        )
        self.op.save()

    # ------------------------------------------------------------------
    # Happy path — no payments, reversal allowed
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

    def test_reversal_is_marked_as_reversal(self):
        reversal = self.op.reverse(officer=self.officer_user)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reverse_inherits_amount_source_destination(self):
        reversal = self.op.reverse(officer=self.officer_user)

        self.assertEqual(reversal.amount, self.op.amount)
        self.assertEqual(reversal.source, self.op.source)
        self.assertEqual(reversal.destination, self.op.destination)

    def test_reverse_creates_counter_transaction_for_issuance(self):
        """Only the EXPENSE_ISSUANCE is implicitly reversed (not one-shot operation)."""
        self.op.reverse(officer=self.officer_user)

        all_txs = self.op.get_all_transactions()
        # 1 original EXPENSE_ISSUANCE + 1 counter-EXPENSE_ISSUANCE
        self.assertEqual(all_txs.count(), 2)

        counter_txs = all_txs.filter(reversal_of__isnull=False)
        self.assertEqual(counter_txs.count(), 1)

    def test_reverse_counter_transaction_flips_funds(self):
        self.op.reverse(officer=self.officer_user)

        original_tx = self.op.get_all_transactions().get(reversal_of__isnull=True)
        counter_tx = original_tx.reversed_by

        self.assertEqual(counter_tx.source, original_tx.target)
        self.assertEqual(counter_tx.target, original_tx.source)
        self.assertEqual(counter_tx.amount, original_tx.amount)

    def test_project_fund_unchanged_after_reversal(self):
        """Issuance is non-cash; reversing it leaves the project fund balance untouched."""
        balance_before_reversal = self.project_entity.balance

        self.op.reverse(officer=self.officer_user)

        self.project_entity.refresh_from_db()
        self.assertEqual(self.project_entity.balance, balance_before_reversal)

    # ------------------------------------------------------------------
    # Reversal blocked by existing payment
    # ------------------------------------------------------------------

    def test_reversal_blocked_when_payment_exists(self):
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
