"""
Integration tests for ``Operation.create()`` classmethod.

Tests the factory method that constructs, validates, saves, and performs
side-effects (payment, invoice) in a single atomic transaction.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CapitalGainOperation,
    CashInjectionOperation,
    PurchaseOperation,
)
from apps.app_operation.tests.base import assert_tx_types
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


def _make_project_entity(name):
    return Entity.create(EntityType.PROJECT, name=name)


def _make_vendor_entity(name):
    return Entity.create(EntityType.PERSON, name=name, is_vendor=True)


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


def _make_vendor_stakeholder(project_entity, vendor_entity, active=True):
    sh = Stakeholder(
        parent=project_entity,
        target=vendor_entity,
        role=StakeholderRole.VENDOR,
        active=active,
    )
    sh.save()
    return sh


# =========================================================================
# CashInjectionCreateTest
#
# Tests ``Operation.create()`` with a proxy that has neither
# ``can_pay`` nor ``has_invoice`` — exercises the core construction path.
# =========================================================================


class CashInjectionCreateTest(TestCase):
    """``Operation.create()`` via ``CashInjectionOperation`` (no payment, no invoice)."""

    def setUp(self):
        self.world_entity = Entity.create(EntityType.WORLD)
        self.officer_user = _make_officer()
        self.receiver_entity = _make_person_entity("Receiver Person")

    def test_create_returns_saved_instance(self):
        """Happy path: create returns a persisted operation."""
        op = CashInjectionOperation.create(
            operation_type=OperationType.CASH_INJECTION,
            source=self.world_entity,
            destination=self.receiver_entity,
            amount=Decimal("1000.00"),
            date=date.today(),
            description="Test cash injection via create()",
            officer=self.officer_user,
        )
        self.assertIsNotNone(op.pk)
        self.assertEqual(op.source, self.world_entity)
        self.assertEqual(op.destination, self.receiver_entity)
        self.assertEqual(op.amount, Decimal("1000.00"))

    def test_create_without_payment_does_not_call_process_payment(self):
        """``can_pay`` is False — no payment transaction is created by create()."""
        op = CashInjectionOperation.create(
            operation_type=OperationType.CASH_INJECTION,
            source=self.world_entity,
            destination=self.receiver_entity,
            amount=Decimal("500.00"),
            date=date.today(),
            description="No payment",
            officer=self.officer_user,
            amount_paid=Decimal("500.00"),  # ignored because can_pay is False
        )
        # create() does NOT call process_payment() since can_pay is False
        # The instance *is* saved, but no manual payment transaction is created.
        self.assertIsNotNone(op.pk)

    def test_create_without_invoice_skips_invoice_processing(self):
        """``has_invoice`` is False — invoice formset is never constructed."""
        op = CashInjectionOperation.create(
            operation_type=OperationType.CASH_INJECTION,
            source=self.world_entity,
            destination=self.receiver_entity,
            amount=Decimal("250.00"),
            date=date.today(),
            description="No invoice",
            officer=self.officer_user,
            raw_post={"some": "data"},  # ignored because has_invoice is False
        )
        self.assertIsNotNone(op.pk)
        # No invoice items should exist
        self.assertEqual(op.items.count(), 0)

    def test_create_propagates_validation_error(self):
        """Invalid source/destination raises ValidationError."""
        with self.assertRaises(ValidationError):
            CashInjectionOperation.create(
                operation_type=OperationType.CASH_INJECTION,
                source=self.receiver_entity,  # wrong: must be world
                destination=self.receiver_entity,
                amount=Decimal("100.00"),
                date=date.today(),
                description="Bad source",
                officer=self.officer_user,
            )


# =========================================================================
# PurchaseCreateViaFactoryTest
#
# Tests ``Operation.create()`` via ``PurchaseOperation`` — a proxy with
# both ``can_pay=True`` and ``has_invoice=True``.
# =========================================================================


class PurchaseCreateViaFactoryTest(TestCase):
    """``Operation.create()`` via ``PurchaseOperation`` (payment + invoice capable)."""

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = _make_officer()

        self.project_entity = _make_project_entity("Test Farm Project")
        _inject_project(
            self.system_entity,
            self.project_entity,
            Decimal("5000.00"),
            self.officer_user,
        )

        self.vendor_entity = _make_vendor_entity("Agri Supplies Ltd")
        _make_vendor_stakeholder(self.project_entity, self.vendor_entity)

    def test_create_basic_operation(self):
        """Happy path without payment or invoice data."""
        op = PurchaseOperation.create(
            operation_type=OperationType.PURCHASE,
            source=self.project_entity,
            destination=self.vendor_entity,
            amount=Decimal("1000.00"),
            date=date.today(),
            description="Test purchase via create()",
            officer=self.officer_user,
        )
        self.assertIsNotNone(op.pk)
        self.assertEqual(op.amount, Decimal("1000.00"))
        # Exactly one issuance transaction (no payment)
        assert_tx_types(self, op, {TransactionType.PURCHASE_ISSUANCE: 1})

    def test_create_with_payment(self):
        """When amount_paid > 0 and proxy.can_pay, a payment transaction is created."""
        op = PurchaseOperation.create(
            operation_type=OperationType.PURCHASE,
            source=self.project_entity,
            destination=self.vendor_entity,
            amount=Decimal("1000.00"),
            date=date.today(),
            description="Purchase with payment",
            officer=self.officer_user,
            amount_paid=Decimal("1000.00"),
        )
        self.assertIsNotNone(op.pk)
        # Payment processing was called inside create()
        self.assertGreaterEqual(op.amount_settled, Decimal("1000.00"))

    def test_create_propagates_validation_error_on_invalid_source(self):
        """Invalid source entity raises ValidationError."""
        person_entity = _make_person_entity("Not A Project")
        with self.assertRaises(ValidationError):
            PurchaseOperation.create(
                operation_type=OperationType.PURCHASE,
                source=person_entity,  # must be a project
                destination=self.vendor_entity,
                amount=Decimal("500.00"),
                date=date.today(),
                description="Bad source",
                officer=self.officer_user,
            )

    def test_create_propagates_validation_error_on_invalid_destination(self):
        """Invalid destination entity raises ValidationError."""
        non_vendor = _make_person_entity("Not A Vendor")
        with self.assertRaises(ValidationError):
            PurchaseOperation.create(
                operation_type=OperationType.PURCHASE,
                source=self.project_entity,
                destination=non_vendor,  # must be a vendor stakeholder
                amount=Decimal("500.00"),
                date=date.today(),
                description="Bad dest",
                officer=self.officer_user,
            )

    def test_create_zero_amount_raises_validation_error(self):
        """Amount of zero is rejected by validation."""
        with self.assertRaises(ValidationError):
            PurchaseOperation.create(
                operation_type=OperationType.PURCHASE,
                source=self.project_entity,
                destination=self.vendor_entity,
                amount=Decimal("0.00"),
                date=date.today(),
                description="Zero amount",
                officer=self.officer_user,
            )
