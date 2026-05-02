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


class SaleBalanceGuardTest(TestCase):
    """
    Tests that check_balance_on_payment=True on SaleOperation is enforced.

    The client fund balance is seeded below the sale amount so the
    over-collection guard never fires; only the fund-balance check matters.
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.world_entity = Entity.create(EntityType.WORLD)

        self.officer = _make_officer()

        self.project_entity = _make_project_entity("Farm Project")

        self.client_entity = _make_client_entity("Low-Balance Client")
        # Seed only 200 — less than the collection amount we will attempt (600),
        # but the sale itself is for 1000 so the over-collection guard would
        # allow 600.  Only check_balance_on_payment can reject it.
        _seed_client_fund(
            self.world_entity,
            self.client_entity,
            Decimal("200.00"),
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

    def test_check_balance_on_payment_is_enabled(self):
        """Balance is checked before each collection transaction is created."""
        self.assertTrue(SaleOperation.check_balance_on_payment)

    def test_collection_blocked_when_client_fund_has_insufficient_balance(self):
        """check_balance_on_payment=True: collection is rejected when the client
        fund balance is below the requested payment amount, even though the
        remaining-to-settle allows it."""
        with self.assertRaises(ValidationError):
            self.op.create_payment_transaction(
                amount=Decimal("600.00"),
                officer=self.officer,
                date=date.today(),
            )

    def test_collection_succeeds_when_amount_within_client_fund_balance(self):
        """Partial collection that fits within the available fund balance is allowed."""
        self.op.create_payment_transaction(
            amount=Decimal("150.00"),
            officer=self.officer,
            date=date.today(),
        )
        self.client_entity.refresh_from_db()
        self.assertEqual(self.client_entity.balance, Decimal("50.00"))
