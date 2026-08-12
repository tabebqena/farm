from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import InvoiceItem, Product, ProductTemplate
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CapitalGainOperation,
    SaleOperation,
    CashInjectionOperation,
)
from apps.app_operation.tests.base import (
    assert_derived_state_unchanged,
    snapshot_derived_state,
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
    # SE4 — payables / receivables restored on reversal (regression class:
    # reversal mirrors must not leak into the obligation buckets)
    # ------------------------------------------------------------------

    def test_reverse_restores_project_receivables(self):
        """SALE_ISSUANCE makes the project owed by the client; reversal clears it."""
        self.assertEqual(self.project_entity.receivables, Decimal("1000.00"))
        self.op.reverse(officer=self.officer)

        self.assertEqual(self.project_entity.receivables, Decimal("0.00"))

    def test_reverse_restores_client_payables(self):
        """SALE_ISSUANCE makes the client owe the project; reversal clears it."""
        self.assertEqual(self.client_entity.payables, Decimal("1000.00"))
        self.op.reverse(officer=self.officer)

        self.assertEqual(self.client_entity.payables, Decimal("0.00"))

    def test_reverse_project_payables_unchanged(self):
        self.op.reverse(officer=self.officer)

        self.assertEqual(self.project_entity.payables, Decimal("0.00"))

    def test_reverse_client_receivables_unchanged(self):
        self.op.reverse(officer=self.officer)

        self.assertEqual(self.client_entity.receivables, Decimal("0.00"))

    # ------------------------------------------------------------------
    # Differential invariant — create + reverse leaves the world unchanged
    # ------------------------------------------------------------------

    def test_create_then_reverse_leaves_world_unchanged(self):
        """Balances, payables, receivables and ledger must all return to the
        pre-operation state after a full create + reverse cycle."""
        before = snapshot_derived_state()

        op = SaleOperation(
            source=self.client_entity,
            destination=self.project_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.SALE,
            date=date.today(),
            description="Test sale",
            officer=self.officer,
        )
        op.save()
        op.reverse(officer=self.officer)

        assert_derived_state_unchanged(self, before, msg="sale create+reverse")

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
# SE7 — product status restoration on reversal
# ---------------------------------------------------------------------------


class SaleReversalProductStatusRestorationTest(TestCase):
    """Reversing a sale restores a sold product to ACTIVE (SE7)."""

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
        self.template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
        )
        self.template.entities.add(self.project_entity)

    def _make_sold_product(self, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Create a sale whose invoice item links a project-owned product, so
        the product carries SOLD status via the (non-reversed) sale operation."""
        sale = SaleOperation(
            source=self.client_entity,
            destination=self.project_entity,
            amount=(qty * price).quantize(Decimal("0.01")),
            operation_type=OperationType.SALE,
            date=date.today(),
            description="Test sale",
            officer=self.officer,
        )
        sale.save()
        item = InvoiceItem.objects.create(
            operation=sale,
            product_template=self.template,
            quantity=qty,
            unit_price=price,
        )
        product = Product.objects.create(
            product_template=self.template,
            entity=self.project_entity,
            unit_price=price,
            quantity=int(qty),
        )
        product.invoice_items.add(item)
        return sale, product

    def test_sale_links_product_as_sold(self):
        """A product linked to a non-reversed SALE item carries SOLD status."""
        _, product = self._make_sold_product()
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.SOLD)

    def test_reverse_restores_sold_product_to_active(self):
        """Reversing the sale excludes it from the status derivation, so the
        product returns to ACTIVE (SE7)."""
        sale, product = self._make_sold_product()
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.SOLD)

        sale.reverse(officer=self.officer)

        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)


# ---------------------------------------------------------------------------
# SaleBalanceGuardTest
# ---------------------------------------------------------------------------
