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


class AdjustmentReversalTest(TestCase):
    """
    Verify the full reversal lifecycle for Adjustment:
    - reverse() creates a counter-adjustment linked to the original
    - original is marked as reversed; reversal is marked as is_reversal
    - counter-transaction is created with flipped source/target
    - reversed and reversal adjustments are both constraints-checked
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
        self.adj = _make_adjustment(
            self.op, AdjustmentType.PURCHASE_RETURN, self.officer
        )

    def test_reverse_returns_new_adjustment_instance(self):
        reversal = self.adj.reverse(officer=self.officer)

        self.assertIsNotNone(reversal.pk)
        self.assertNotEqual(reversal.pk, self.adj.pk)

    def test_reversal_is_linked_to_original(self):
        reversal = self.adj.reverse(officer=self.officer)

        self.assertEqual(reversal.reversal_of, self.adj)

    def test_original_is_marked_as_reversed(self):
        reversal = self.adj.reverse(officer=self.officer)

        self.adj.refresh_from_db()
        self.assertTrue(self.adj.is_reversed)
        self.assertEqual(self.adj.reversed_by, reversal)

    def test_reversal_is_marked_as_reversal(self):
        reversal = self.adj.reverse(officer=self.officer)

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reversal_inherits_type_amount_operation(self):
        reversal = self.adj.reverse(officer=self.officer)

        self.assertEqual(reversal.operation, self.adj.operation)
        self.assertEqual(reversal.type, self.adj.type)
        self.assertEqual(reversal.amount, self.adj.amount)

    def test_reverse_creates_counter_transaction(self):
        """Original has 1 PURCHASE_ADJUSTMENT; after reversal there should be 2."""
        self.adj.reverse(officer=self.officer)

        all_txs = self.adj.get_all_transactions()
        self.assertEqual(all_txs.count(), 2)
        self.assertEqual(all_txs.filter(reversal_of__isnull=False).count(), 1)

    def test_counter_transaction_flips_source_and_target(self):
        self.adj.reverse(officer=self.officer)

        original_tx = self.adj.get_all_transactions().get(reversal_of__isnull=True)
        counter_tx = original_tx.reversed_by

        self.assertEqual(counter_tx.source, original_tx.target)
        self.assertEqual(counter_tx.target, original_tx.source)
        self.assertEqual(counter_tx.amount, original_tx.amount)

    def test_cannot_reverse_already_reversed_adjustment(self):
        self.adj.reverse(officer=self.officer)
        self.adj.refresh_from_db()

        with self.assertRaises(ValidationError):
            self.adj.reverse(officer=self.officer)

    def test_cannot_reverse_a_reversal(self):
        reversal = self.adj.reverse(officer=self.officer)

        with self.assertRaises(ValidationError):
            reversal.reverse(officer=self.officer)
