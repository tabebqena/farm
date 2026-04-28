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


class SaleCreateTest(TestCase):
    """
    Tests for sale operation creation: validation, issuance transaction, and
    fund behaviour.

    On save, only a SALE_ISSUANCE transaction is created (receivable record).
    SALE_ISSUANCE is a non-cash transaction — it does NOT affect fund balances.
    Cash movement only happens later via create_payment_transaction() (collection).
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.world_entity = Entity.create(EntityType.WORLD)

        self.officer = _make_officer()

        self.project_entity = _make_project_entity("Test Farm Project")

        self.client_entity = _make_client_entity("Big Buyer Corp")
        _seed_client_fund(
            self.world_entity,
            self.client_entity,
            Decimal("5000.00"),
            self.officer,
        )
        _make_client_stakeholder(self.project_entity, self.client_entity)

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.client_entity,
            destination=self.project_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.SALE,
            date=date.today(),
            description="Test sale",
            officer=self.officer,
        )
        defaults.update(kwargs)
        return SaleOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path — issuance only on creation
    # ------------------------------------------------------------------

    def test_save_creates_exactly_one_issuance_transaction(self):
        op = self._make_op()
        op.save()

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 1)
        self.assertTrue(
            transactions.filter(type=TransactionType.SALE_ISSUANCE).exists(),
            "Issuance transaction must be created on save",
        )

    def test_no_collection_transaction_created_on_save(self):
        op = self._make_op()
        op.save()

        self.assertFalse(
            op.get_all_transactions()
            .filter(type=TransactionType.SALE_COLLECTION)
            .exists(),
            "Collection transaction must NOT be created on save — sale is not one-shot",
        )

    def test_issuance_transaction_direction_is_client_to_project(self):
        op = self._make_op()
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.SALE_ISSUANCE)
        self.assertEqual(tx.source, self.client_entity)
        self.assertEqual(tx.target, self.project_entity)

    def test_issuance_transaction_amount_matches_operation(self):
        op = self._make_op(amount=Decimal("750.00"))
        op.save()

        tx = op.get_all_transactions().get(type=TransactionType.SALE_ISSUANCE)
        self.assertEqual(tx.amount, Decimal("750.00"))

    def test_project_fund_balance_unchanged_after_save(self):
        """SALE_ISSUANCE is non-cash; it does not affect fund balances."""
        balance_before = self.project_entity.balance

        op = self._make_op(amount=Decimal("800.00"))
        op.save()

        self.project_entity.refresh_from_db()
        self.assertEqual(self.project_entity.balance, balance_before)

    def test_client_fund_balance_unchanged_after_save(self):
        """SALE_ISSUANCE is non-cash; it does not affect fund balances."""
        balance_before = self.client_entity.balance

        op = self._make_op(amount=Decimal("800.00"))
        op.save()

        self.client_entity.refresh_from_db()
        self.assertEqual(self.client_entity.balance, balance_before)

    def test_amount_remaining_to_settle_equals_full_amount_after_creation(self):
        op = self._make_op(amount=Decimal("1200.00"))
        op.save()

        self.assertEqual(op.amount_remaining_to_settle, Decimal("1200.00"))

    def test_is_not_fully_settled_after_creation(self):
        op = self._make_op()
        op.save()

        self.assertFalse(op.is_fully_settled)

    # ------------------------------------------------------------------
    # Source validation — must be a client entity
    # ------------------------------------------------------------------

    def test_source_must_be_a_client_entity(self):
        non_client = _make_person_entity("Not A Client")
        op = self._make_op(source=non_client)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_project_entity_raises_validation_error(self):
        other_project = _make_project_entity("Some Project")
        op = self._make_op(source=other_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_must_be_active(self):
        self.client_entity.active = False
        self.client_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_fund_must_be_active(self):
        self.client_entity.active = False
        self.client_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation — must be a project entity
    # ------------------------------------------------------------------

    def test_destination_must_be_a_project_entity(self):
        non_project = _make_person_entity("Not A Project")
        op = self._make_op(destination=non_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_must_be_active_stakeholder_project(self):
        unregistered_project = _make_project_entity("Unregistered Project")
        # is a project but no Stakeholder relationship with this client
        op = self._make_op(destination=unregistered_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_with_inactive_stakeholder_raises_validation_error(self):
        inactive_project = _make_project_entity("Inactive Relationship Project")
        _make_client_stakeholder(inactive_project, self.client_entity, active=False)

        op = self._make_op(destination=inactive_project)
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
        self.officer.is_active = False
        self.officer.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------

    def test_source_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        other_client = _make_client_entity("Other Client")
        _make_client_stakeholder(self.project_entity, other_client)
        op.source = other_client
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        other_project = _make_project_entity("Other Project")
        _make_client_stakeholder(other_project, self.client_entity)
        op.destination = other_project
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_is_immutable_after_save(self):
        op = self._make_op()
        op.save()

        op.amount = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            op.save()


# ---------------------------------------------------------------------------
# SaleCollectionTest
# ---------------------------------------------------------------------------
