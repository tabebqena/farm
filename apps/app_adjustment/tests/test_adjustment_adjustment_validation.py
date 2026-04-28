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


class AdjustmentValidationTest(TestCase):
    """
    Validate business rules enforced in Adjustment.clean():
    - Only PURCHASE, SALE, EXPENSE operations may be adjusted
    - General types require a reason
    - Amount must be positive
    - Officer must be an active staff person with an auth user
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.world_entity = Entity.create(EntityType.WORLD)
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

    def _adj(self, **kwargs):
        defaults = dict(
            operation=self.op,
            type=AdjustmentType.PURCHASE_RETURN,
            amount=Decimal("100.00"),
            reason="",
            date=date.today(),
            officer=self.officer,
        )
        defaults.update(kwargs)
        adj = Adjustment(**defaults)
        adj.save()
        return adj

    # ------------------------------------------------------------------
    # Operation type validation
    # ------------------------------------------------------------------

    def test_non_adjustable_operation_type_raises_validation_error(self):
        """Cash injection operations cannot be adjusted."""
        from apps.app_operation.models.proxies import CashInjectionOperation

        # Cash injection: source=world, destination=person
        recipient = _make_person_entity("Recipient")
        cash_op = CashInjectionOperation(
            source=self.world_entity,
            destination=recipient,
            amount=Decimal("500.00"),
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            officer=self.officer,
        )
        cash_op.save()

        with self.assertRaises(ValidationError):
            self._adj(operation=cash_op)

    def test_purchase_operation_is_adjustable(self):
        adj = self._adj()
        self.assertIsNotNone(adj.pk)

    def test_sale_operation_is_adjustable(self):
        client = _make_client_entity("Client Co")
        _make_client_stakeholder(self.project_entity, client)
        # _inject_project(self.system_entity, client, Decimal("2000.00"), self.officer)
        CashInjectionOperation(
            source=self.world_entity,
            destination=client,
            amount=Decimal("2000.00"),
            operation_type=OperationType.CASH_INJECTION,
            date=date.today(),
            description="Setup injection",
            officer=self.officer,
        ).save()
        sale_op = _make_sale_op(client, self.project_entity, self.officer)

        adj = self._adj(operation=sale_op, type=AdjustmentType.SALE_RETURN)
        self.assertIsNotNone(adj.pk)

    # ------------------------------------------------------------------
    # General type requires reason
    # ------------------------------------------------------------------

    def test_general_reduction_without_reason_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._adj(type=AdjustmentType.PURCHASE_GENERAL_REDUCTION, reason="")

    def test_general_increase_without_reason_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._adj(type=AdjustmentType.PURCHASE_GENERAL_INCREASE, reason="")

    def test_general_reduction_with_reason_saves_ok(self):
        adj = self._adj(
            type=AdjustmentType.PURCHASE_GENERAL_REDUCTION, reason="Miscounted items"
        )
        self.assertIsNotNone(adj.pk)

    def test_non_general_type_without_reason_saves_ok(self):
        adj = self._adj(type=AdjustmentType.PURCHASE_RETURN, reason="")
        self.assertIsNotNone(adj.pk)

    # ------------------------------------------------------------------
    # Amount validation (AmountCleanMixin)
    # ------------------------------------------------------------------

    def test_amount_zero_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._adj(amount=Decimal("0.00"))

    def test_amount_negative_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._adj(amount=Decimal("-50.00"))

    # ------------------------------------------------------------------
    # Officer validation (OfficerMixin)
    # ------------------------------------------------------------------

    def test_officer_user_must_be_staff(self):
        non_staff_user = User.objects.create_user(
            username="non_staff", password="x", is_staff=False
        )
        with self.assertRaises(ValidationError):
            self._adj(officer=non_staff_user)

    def test_officer_must_be_active(self):
        self.officer.is_active = False
        self.officer.save()
        with self.assertRaises(ValidationError):
            self._adj()


# ---------------------------------------------------------------------------
# AdjustmentImmutabilityTest
# ---------------------------------------------------------------------------
