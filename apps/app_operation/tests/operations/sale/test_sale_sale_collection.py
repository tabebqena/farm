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


class SaleCollectionTest(TestCase):
    """
    Tests for SALE_COLLECTION transactions.

    The project records a sale receivable on save (SALE_ISSUANCE, non-cash).
    Collections are created explicitly and move funds: client → project.
    Multiple partial collections are allowed, up to the total operation amount.
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.world_entity = Entity.create(EntityType.WORLD)

        self.officer = _make_officer()

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

    def _collect(self, amount):
        self.op.create_payment_transaction(
            amount=amount,
            officer=self.officer,
            date=date.today(),
        )

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_collection_creates_sale_collection_transaction(self):
        self._collect(Decimal("400.00"))

        collection_txs = self.op.get_all_transactions().filter(
            type=TransactionType.SALE_COLLECTION
        )
        self.assertEqual(collection_txs.count(), 1)

    def test_collection_transaction_direction_is_client_to_project(self):
        self._collect(Decimal("400.00"))

        tx = self.op.get_all_transactions().get(type=TransactionType.SALE_COLLECTION)
        self.assertEqual(tx.source, self.client_entity)
        self.assertEqual(tx.target, self.project_entity)

    def test_amount_remaining_to_settle_decreases_after_collection(self):
        self._collect(Decimal("400.00"))

        self.assertEqual(self.op.amount_remaining_to_settle, Decimal("600.00"))

    def test_multiple_partial_collections_are_allowed(self):
        self._collect(Decimal("300.00"))
        self._collect(Decimal("300.00"))
        self._collect(Decimal("400.00"))

        collection_txs = self.op.get_all_transactions().filter(
            type=TransactionType.SALE_COLLECTION
        )
        self.assertEqual(collection_txs.count(), 3)
        self.assertEqual(self.op.amount_remaining_to_settle, Decimal("0.00"))

    def test_multiple_collections_accumulate_correctly(self):
        self._collect(Decimal("250.00"))
        self._collect(Decimal("350.00"))

        self.assertEqual(self.op.amount_settled, Decimal("600.00"))
        self.assertEqual(self.op.amount_remaining_to_settle, Decimal("400.00"))

    def test_full_collection_marks_operation_as_fully_settled(self):
        self._collect(Decimal("1000.00"))

        self.assertTrue(self.op.is_fully_settled)
        self.assertEqual(self.op.amount_remaining_to_settle, Decimal("0.00"))

    def test_client_fund_decreases_by_collection_amount(self):
        balance_before = self.client_entity.balance

        self._collect(Decimal("600.00"))

        self.client_entity.refresh_from_db()
        self.assertEqual(
            self.client_entity.balance,
            balance_before - Decimal("600.00"),
        )

    def test_project_fund_increases_by_collection_amount(self):
        balance_before = self.project_entity.balance

        self._collect(Decimal("600.00"))

        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            balance_before + Decimal("600.00"),
        )

    def test_total_transactions_after_partial_collection_is_two(self):
        """One issuance (created on save) + one collection = two transactions."""
        self._collect(Decimal("500.00"))

        self.assertEqual(self.op.get_all_transactions().count(), 2)

    # ------------------------------------------------------------------
    # Over-collection blocked
    # ------------------------------------------------------------------

    def test_collection_exceeding_operation_amount_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._collect(Decimal("1500.00"))

    def test_partial_collection_then_over_collection_raises_validation_error(self):
        self._collect(Decimal("800.00"))

        with self.assertRaises(ValidationError):
            self._collect(Decimal("300.00"))  # only 200 remaining

    def test_zero_collection_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._collect(Decimal("0.00"))

    def test_negative_collection_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._collect(Decimal("-100.00"))


# ---------------------------------------------------------------------------
# SaleReversalTest
# ---------------------------------------------------------------------------
