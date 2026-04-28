from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_adjustment.models import Adjustment, AdjustmentType
from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CapitalGainOperation,
    ExpenseOperation,
    PurchaseOperation,
    SaleOperation,
)
from apps.app_operation.models.proxies.op_cash_injection import CashInjectionOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username="officer"):
    return User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def _make_project_entity(name):
    return Entity.create(EntityType.PROJECT, name=name)


def _make_person_entity(name):
    return Entity.create(EntityType.PERSON, name=name)


def _make_vendor_entity(name):
    return Entity.create(EntityType.PROJECT, name=name, is_vendor=True)


def _make_client_entity(name):
    return Entity.create(EntityType.PERSON, name=name, is_client=True)


def _make_vendor_stakeholder(project_entity, vendor_entity, active=True):
    sh = Stakeholder(
        parent=project_entity,
        target=vendor_entity,
        role=StakeholderRole.VENDOR,
        active=active,
    )
    sh.save()
    return sh


def _make_client_stakeholder(project_entity, client_entity, active=True):
    sh = Stakeholder(
        parent=project_entity,
        target=client_entity,
        role=StakeholderRole.CLIENT,
        active=active,
    )
    sh.save()
    return sh


def _inject_project(system_entity, dest_entity, amount, officer_user):
    CapitalGainOperation(
        source=system_entity,
        destination=dest_entity,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
        date=date.today(),
        description="Seed balance",
        officer=officer_user,
    ).save()


def _make_purchase_op(
    project_entity, vendor_entity, officer_user, amount=Decimal("1000.00")
):
    op = PurchaseOperation(
        source=project_entity,
        destination=vendor_entity,
        amount=amount,
        operation_type=OperationType.PURCHASE,
        date=date.today(),
        description="Test purchase",
        officer=officer_user,
    )
    op.save()
    return op


def _make_sale_op(
    client_entity, project_entity, officer_user, amount=Decimal("1000.00")
):
    op = SaleOperation(
        source=client_entity,
        destination=project_entity,
        amount=amount,
        operation_type=OperationType.SALE,
        date=date.today(),
        description="Test sale",
        officer=officer_user,
    )
    op.save()
    return op


def _make_expense_op(
    project_entity, world_entity, officer_user, amount=Decimal("1000.00")
):
    op = ExpenseOperation(
        source=project_entity,
        destination=world_entity,
        amount=amount,
        operation_type=OperationType.EXPENSE,
        date=date.today(),
        description="Test expense",
        officer=officer_user,
    )
    op.save()
    return op


def _make_adjustment(operation, adj_type, officer, amount=Decimal("100.00"), reason=""):
    adj = Adjustment(
        operation=operation,
        type=adj_type,
        amount=amount,
        reason=reason,
        date=date.today(),
        officer=officer,
    )
    adj.save()
    return adj


# ---------------------------------------------------------------------------
# AdjustmentTransactionTest
# ---------------------------------------------------------------------------


class AdjustmentTransactionTest(TestCase):
    """
    Verify that saving an Adjustment creates exactly one issuance transaction
    of the correct type, matching the parent operation type.
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.world_entity = Entity.create(EntityType.WORLD)
        self.officer = _make_officer()

        self.project_entity = _make_project_entity("Test Farm Project")
        _inject_project(
            self.system_entity, self.project_entity, Decimal("5000.00"), self.officer
        )

        self.vendor_entity = _make_vendor_entity("Vendor Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

        self.client_entity = _make_client_entity("Client Co")
        _make_client_stakeholder(self.project_entity, self.client_entity)
        # _inject_project(
        #     self.system_entity, self.client_entity, Decimal("5000.00"), self.officer
        # )
        CashInjectionOperation(
            source=self.world_entity,
            destination=self.client_entity,
            amount=Decimal("5000.00"),
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            description="Setup injection",
            officer=self.officer,
        ).save()

    def test_purchase_adjustment_creates_purchase_adjustment_transaction(self):
        op = _make_purchase_op(self.project_entity, self.vendor_entity, self.officer)
        adj = _make_adjustment(op, AdjustmentType.PURCHASE_RETURN, self.officer)

        txs = adj.get_all_transactions()
        self.assertEqual(txs.count(), 1)
        self.assertTrue(
            txs.filter(type=TransactionType.PURCHASE_ADJUSTMENT_DECREASE).exists()
        )

    def test_sale_adjustment_creates_sale_adjustment_transaction(self):
        op = _make_sale_op(self.client_entity, self.project_entity, self.officer)
        adj = _make_adjustment(op, AdjustmentType.SALE_RETURN, self.officer)

        txs = adj.get_all_transactions()
        self.assertEqual(txs.count(), 1)
        self.assertTrue(
            txs.filter(type=TransactionType.SALE_ADJUSTMENT_DECREASE).exists()
        )

    def test_expense_adjustment_creates_expense_adjustment_transaction(self):
        op = _make_expense_op(self.project_entity, self.world_entity, self.officer)
        adj = _make_adjustment(op, AdjustmentType.PURCHASE_RETURN, self.officer)

        txs = adj.get_all_transactions()
        self.assertEqual(txs.count(), 1)
        self.assertTrue(
            txs.filter(type=TransactionType.EXPENSE_ADJUSTMENT_DECREASE).exists()
        )

    def test_adjustment_transaction_source_and_target_match_adjustment_funds(self):
        """Transaction direction must match the adjustment's own source/target funds.

        For reduction types (e.g. PURCHASE_RETURN) the direction is reversed
        relative to the operation: vendor pays project, not project pays vendor.
        """
        op = _make_purchase_op(self.project_entity, self.vendor_entity, self.officer)
        adj = _make_adjustment(op, AdjustmentType.PURCHASE_RETURN, self.officer)

        tx = adj.get_all_transactions().get()
        self.assertEqual(tx.source, adj.payment_source_fund)  # vendor
        self.assertEqual(tx.target, adj.payment_target_fund)  # project

    def test_adjustment_transaction_amount_matches_adjustment(self):
        op = _make_purchase_op(self.project_entity, self.vendor_entity, self.officer)
        adj = _make_adjustment(
            op, AdjustmentType.PURCHASE_RETURN, self.officer, amount=Decimal("250.00")
        )

        tx = adj.get_all_transactions().get()
        self.assertEqual(tx.amount, Decimal("250.00"))


# ---------------------------------------------------------------------------
# AdjustmentDirectionTest
# ---------------------------------------------------------------------------
