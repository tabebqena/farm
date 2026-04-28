from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (

    CapitalGainOperation,
    SaleOperation,
    CashInjectionOperation,
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


def _make_person_entity(name):
    return Entity.create(EntityType.PERSON, name=name)
    return person.entity


def _make_project_entity(name):
    return Entity.create(EntityType.PROJECT, name=name)


def _make_client_entity(name):
    return Entity.create(EntityType.PERSON, name=name, is_client=True)


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


def _seed_client_fund(world_entity, client_entity, amount, officer):
    """Seed a Client entity's fund via CapitalGain so collections can deduct from it."""
    CashInjectionOperation(
        source=world_entity,
        destination=client_entity,
        amount=amount,
        operation_type=OperationType.CASH_INJECTION,
        date=date.today(),
        description="Seed client balance",
        officer=officer,
    ).save()


def _make_client_stakeholder(project_entity, client_entity, active=True):
    sh = Stakeholder(
        parent=project_entity,
        target=client_entity,
        role=StakeholderRole.CLIENT,
        active=active,
    )
    sh.save()
    return sh


# ---------------------------------------------------------------------------
# SaleCreateTest
# ---------------------------------------------------------------------------



class SaleReversalTest(TestCase):
    """
    Tests for sale operation reversal.

    Reversal is allowed only when no SALE_COLLECTION transactions exist.
    Reversing the operation creates a counter-transaction for the issuance.
    Since SALE_ISSUANCE is non-cash, fund balances are unaffected by reversal.
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer = _make_officer()
        self.world_entity = Entity.create(EntityType.WORLD)

        self.project_entity = _make_project_entity("Farm Project")

        self.client_entity = _make_client_entity("Big Buyer Corp")
        _seed_client_fund(
            self.world_entity,
            self.client_entity,
            Decimal("5000.00"),
            self.officer,
        )
        _make_client_stakeholder(self.project_entity, self.client_entity)

        self.op = SaleOperation(
            source=self.client_entity,
            destination=self.project_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.SALE,
            date=date.today(),
            description="Test sale",
            officer=self.officer,
        )
        self.op.save()

    # ------------------------------------------------------------------
    # Happy path — no collections, reversal allowed
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

    def test_reversal_is_marked_as_reversal(self):
        reversal = self.op.reverse(officer=self.officer)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reverse_inherits_amount_source_destination(self):
        reversal = self.op.reverse(officer=self.officer)

        self.assertEqual(reversal.amount, self.op.amount)
        self.assertEqual(reversal.source, self.op.source)
        self.assertEqual(reversal.destination, self.op.destination)

    def test_reverse_creates_counter_transaction_for_issuance(self):
        """Only the SALE_ISSUANCE is implicitly reversed (not one-shot operation)."""
        self.op.reverse(officer=self.officer)

        all_txs = self.op.get_all_transactions()
        # 1 original SALE_ISSUANCE + 1 counter-SALE_ISSUANCE
        self.assertEqual(all_txs.count(), 2)

        counter_txs = all_txs.filter(reversal_of__isnull=False)
        self.assertEqual(counter_txs.count(), 1)

    def test_reverse_counter_transaction_flips_funds(self):
        self.op.reverse(officer=self.officer)

        original_tx = self.op.get_all_transactions().get(reversal_of__isnull=True)
        counter_tx = original_tx.reversed_by

        self.assertEqual(counter_tx.source, original_tx.target)
        self.assertEqual(counter_tx.target, original_tx.source)
        self.assertEqual(counter_tx.amount, original_tx.amount)

    def test_fund_balances_unchanged_after_reversal(self):
        """Issuance is non-cash; reversing it leaves all fund balances untouched."""
        project_balance_before = self.project_entity.balance
        client_balance_before = self.client_entity.balance

        self.op.reverse(officer=self.officer)

        self.project_entity.refresh_from_db()
        self.client_entity.refresh_from_db()
        self.assertEqual(self.project_entity.balance, project_balance_before)
        self.assertEqual(self.client_entity.balance, client_balance_before)

    # ------------------------------------------------------------------
    # Reversal blocked by existing collection
    # ------------------------------------------------------------------

    def test_reversal_blocked_when_collection_exists(self):
        self.op.create_payment_transaction(
            amount=Decimal("500.00"),
            officer=self.officer,
            date=date.today(),
        )

        with self.assertRaises(ValidationError):
            self.op.reverse(officer=self.officer)

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


# ---------------------------------------------------------------------------
# SaleBalanceGuardTest
# ---------------------------------------------------------------------------
