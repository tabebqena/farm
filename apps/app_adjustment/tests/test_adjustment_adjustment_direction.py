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


class AdjustmentDirectionTest(TestCase):
    """
    Verify that direction (payment_source_fund / payment_target_fund) is
    correctly derived from `type`.

    Reduction types flow in the reversed direction relative to the parent
    operation (operation's target pays operation's source).
    Increase types flow in the same direction as the parent operation.
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer = _make_officer()

        self.project_entity = _make_project_entity("Test Farm")
        _inject_project(
            self.system_entity, self.project_entity, Decimal("5000.00"), self.officer
        )

        self.vendor_entity = _make_vendor_entity("Vendor Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

        self.op = _make_purchase_op(
            self.project_entity, self.vendor_entity, self.officer
        )

    def _adj(self, adj_type, reason=""):
        return _make_adjustment(self.op, adj_type, self.officer, reason=reason)

    # Reduction types: direction reversed → vendor pays project
    def test_purchase_return_reverses_direction(self):
        adj = self._adj(AdjustmentType.PURCHASE_RETURN)
        self.assertEqual(adj.payment_source_fund, self.vendor_entity)
        self.assertEqual(adj.payment_target_fund, self.project_entity)

    def test_purchase_discount_reverses_direction(self):
        adj = self._adj(AdjustmentType.PURCHASE_DISCOUNT)
        self.assertEqual(adj.payment_source_fund, self.vendor_entity)
        self.assertEqual(adj.payment_target_fund, self.project_entity)

    def test_purchase_general_reduction_reverses_direction(self):
        adj = self._adj(
            AdjustmentType.PURCHASE_GENERAL_REDUCTION, reason="Typo in invoice"
        )
        self.assertEqual(adj.payment_source_fund, self.vendor_entity)
        self.assertEqual(adj.payment_target_fund, self.project_entity)

    # Increase types: direction normal → project pays vendor
    def test_purchase_undercharge_keeps_direction(self):
        adj = self._adj(AdjustmentType.PURCHASE_UNDERCHARGE)
        self.assertEqual(adj.payment_source_fund, self.project_entity)
        self.assertEqual(adj.payment_target_fund, self.vendor_entity)

    def test_purchase_freight_keeps_direction(self):
        adj = self._adj(AdjustmentType.PURCHASE_FREIGHT)
        self.assertEqual(adj.payment_source_fund, self.project_entity)
        self.assertEqual(adj.payment_target_fund, self.vendor_entity)

    def test_purchase_general_increase_keeps_direction(self):
        adj = self._adj(
            AdjustmentType.PURCHASE_GENERAL_INCREASE, reason="Missed line item"
        )
        self.assertEqual(adj.payment_source_fund, self.project_entity)
        self.assertEqual(adj.payment_target_fund, self.vendor_entity)


# ---------------------------------------------------------------------------
# AdjustmentValidationTest
# ---------------------------------------------------------------------------
