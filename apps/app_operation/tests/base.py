"""Shared fixtures and exact-value side-effect assertions for operation tests.

Centralizes the fixtures that were copy-pasted across every operation test file
and provides assertion helpers that pin **one side effect at a time** with exact
values (see ``ai-plans/improve-operation-test-suite-plan.md``).

Side-effect IDs referenced below (SE1..SE12) are defined in the plan's catalog.
"""
from collections import Counter
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import Product
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CashInjectionOperation, CorrectionOperation

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_officer(username="officer"):
    """An active staff user used as the officer on every operation."""
    return User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def make_project(name="Test Farm Project"):
    return Entity.create(EntityType.PROJECT, name)


def make_person(name, is_worker=False):
    return Entity.create(EntityType.PERSON, name=name, is_worker=is_worker)


def make_client(name, is_client=True):
    return Entity.create(EntityType.CLIENT, name=name, is_client=is_client)


def make_vendor(name):
    return Entity.create(EntityType.VENDOR, name)


def make_stakeholder(parent, target, role=StakeholderRole.WORKER, active=True):
    sh = Stakeholder(parent=parent, target=target, role=role, active=active)
    sh.save()
    return sh


def make_worker(project, name="Ali Worker", role=StakeholderRole.WORKER, active=True):
    """A PERSON entity flagged as a worker and linked to ``project`` as stakeholder."""
    worker = Entity.create(EntityType.PERSON, name=name, is_worker=True)
    make_stakeholder(project, worker, role=role, active=active)
    return worker


def inject_person_fund(world, dest, amount, officer):
    """Seed a Person entity's fund via a CashInjection (world -> person)."""
    CashInjectionOperation(
        source=world,
        destination=dest,
        amount=amount,
        operation_type=OperationType.CASH_INJECTION,
        date=date.today(),
        description="Seed balance",
        officer=officer,
    ).save()


def inject_project_fund(system, dest, amount, officer):
    """Seed a Project entity's fund with real cash via a CorrectionCredit
    (system -> project). A CapitalGain is non-cash (its *_PAYMENT is excluded
    from ``payment_types()``), so it cannot fund a project's spendable balance."""
    CorrectionOperation(
        source=system,
        destination=dest,
        amount=amount,
        operation_type=OperationType.CORRECTION_CREDIT,
        date=date.today(),
        description="Seed project balance",
        officer=officer,
    ).save()


def build_worker_advance(project, worker, officer, amount, **kwargs):
    """An UNSAVED WorkerAdvanceOperation (so tests can trigger save() errors)."""
    from apps.app_operation.models.proxies import WorkerAdvanceOperation

    defaults = dict(
        source=project,
        destination=worker,
        amount=amount,
        operation_type=OperationType.WORKER_ADVANCE,
        date=kwargs.pop("date", date.today()),
        description=kwargs.pop("description", "Test worker advance"),
        officer=officer,
    )
    defaults.update(kwargs)
    return WorkerAdvanceOperation(**defaults)


def make_worker_advance(project, worker, officer, amount, **kwargs):
    """A saved WorkerAdvanceOperation with its one-shot transactions."""
    op = build_worker_advance(project, worker, officer, amount, **kwargs)
    op.save()
    return op


# ---------------------------------------------------------------------------
# Base test case: canonical world
# ---------------------------------------------------------------------------


class BaseOperationTestCase(TestCase):
    """Canonical world: system + world entities, an officer, a pre-funded project."""

    project_funding = Decimal("5000.00")

    def setUp(self):
        self.system = Entity.create(EntityType.SYSTEM)
        self.world = Entity.create(EntityType.WORLD)
        self.officer = make_officer()
        self.project = make_project("Test Farm Project")
        inject_project_fund(self.system, self.project, self.project_funding, self.officer)

    # ------------------------------------------------------------------
    # SE2 — transactions
    # ------------------------------------------------------------------

    def assert_tx(self, op, tx_type, source, target, amount, *, reversal_of=None):
        """Exactly one ``tx_type`` transaction exists with exact fields (SE2)."""
        qs = op.get_all_transactions().filter(type=tx_type)
        self.assertEqual(
            qs.count(), 1, f"Expected exactly one {tx_type} transaction for op {op.pk}"
        )
        tx = qs.get()
        self.assertEqual(tx.source, source, f"source of {tx_type}")
        self.assertEqual(tx.target, target, f"target of {tx_type}")
        self.assertEqual(tx.amount, amount, f"amount of {tx_type}")
        if reversal_of is None:
            self.assertIsNone(tx.reversal_of, f"{tx_type} must not be a reversal")
        else:
            self.assertEqual(tx.reversal_of, reversal_of, f"reversal_of of {tx_type}")
        return tx

    def assert_tx_types(self, op, expected):
        """Assert the operation's full transaction type/count map (SE2)."""
        assert_tx_types(self, op, expected)

    def assert_counter_tx(self, original):
        """Assert ``original`` is reversed by an exact mirror transaction (SE2).

        The counter keeps the same type/amount and swaps source/target, and links
        back to the original via ``reversal_of``.
        """
        counter = original.reversed_by
        self.assertIsNotNone(counter, f"{original.type} must be reversed")
        self.assertEqual(counter.source, original.target, "counter.source")
        self.assertEqual(counter.target, original.source, "counter.target")
        self.assertEqual(counter.amount, original.amount, "counter.amount")
        self.assertEqual(counter.type, original.type, "counter.type")
        self.assertEqual(counter.reversal_of, original, "counter.reversal_of")
        return counter

    # ------------------------------------------------------------------
    # SE3 / SE4 — entity balance, payables, receivables
    # ------------------------------------------------------------------

    def assert_balance(self, entity, expected, *, msg=""):
        self.assertEqual(
            entity.balance, expected, f"{msg or entity}.balance"
        )

    def assert_payables(self, entity, expected, *, msg=""):
        self.assertEqual(
            entity.payables, expected, f"{msg or entity}.payables"
        )

    def assert_receivables(self, entity, expected, *, msg=""):
        self.assertEqual(
            entity.receivables, expected, f"{msg or entity}.receivables"
        )

    # ------------------------------------------------------------------
    # SE6 / SE7 — movement lines and product status
    # ------------------------------------------------------------------

    def assert_movement(self, op, *, product=None, qty=None, reversal_of=None, count=1):
        qs = op.movement_lines
        if product is not None:
            qs = qs.filter(product=product)
        if qty is not None:
            qs = qs.filter(quantity=qty)
        if reversal_of is not None:
            qs = qs.filter(reversal_of=reversal_of)
        self.assertEqual(qs.count(), count)
        return qs.first()

    def assert_product_status(self, product, status, *, msg=""):
        product.refresh_from_db()
        self.assertEqual(product.status, status, f"{msg or product}.status")

    # ------------------------------------------------------------------
    # Differential invariant helpers (create+reverse leaves world unchanged)
    # ------------------------------------------------------------------

    def _ledger_totals(self):
        return _ledger_totals()

    def snapshot_state(self):
        return snapshot_derived_state()

    def assert_state_unchanged(self, before, *, msg=""):
        assert_derived_state_unchanged(self, before, msg=msg)


# ---------------------------------------------------------------------------
# Module-level helpers (usable from any TestCase, not only
# BaseOperationTestCase subclasses).
# ---------------------------------------------------------------------------


def assert_tx_types(test_case, op, expected):
    """Assert the operation's full transaction type/count map (SE2).

    Works from any ``TestCase`` (not only ``BaseOperationTestCase`` subclasses)
    so standalone test files can pin the exact transaction type set.
    """
    actual = Counter(op.get_all_transactions().values_list("type", flat=True))
    test_case.assertEqual(dict(actual), dict(expected))


def _ledger_totals():
    """Net quantity/value per product computed from the active movement lines
    plus capital operations (replaces the removed ledger table). Products with
    a zero net state are omitted so reversal mirrors do not break the check."""
    from apps.app_inventory.stock import movement_state

    totals = {}
    for product in Product.objects.all().iterator():
        state = movement_state(product)
        if state["quantity"] != 0 or state["value"] != 0:
            totals[product.pk] = (state["quantity"], state["value"])
    return totals


def snapshot_derived_state():
    """Derived financial state: every real entity's balance/payables/receivables
    plus net ledger totals. Row counts are intentionally excluded so that
    reversal mirrors / audit rows do not break the differential check."""
    entities = Entity.objects.exclude(
        entity_type__in=[EntityType.SYSTEM, EntityType.WORLD]
    )
    return {
        "entities": {
            e.pk: (e.balance, e.payables, e.receivables) for e in entities
        },
        "ledger": _ledger_totals(),
    }


def assert_derived_state_unchanged(test_case, before, *, msg=""):
    """Assert the world snapshot equals ``before`` — used after create+reverse."""
    test_case.assertEqual(
        snapshot_derived_state(), before, f"world state changed: {msg}"
    )
