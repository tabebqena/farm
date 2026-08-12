"""Shared fixtures and exact-value side-effect assertions for operation tests.

Centralizes the fixtures that were copy-pasted across every operation test file
and provides assertion helpers that pin **one side effect at a time** with exact
values (see ``ai-plans/improve-operation-test-suite-plan.md``).

Side-effect IDs referenced below (SE1..SE12) are defined in the plan's catalog.
"""
import importlib
from collections import Counter
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import Product, ProductLedgerEntry
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalGainOperation, CashInjectionOperation

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
    """Seed a Project entity's fund via a CapitalGain (system -> project)."""
    CapitalGainOperation(
        source=system,
        destination=dest,
        amount=amount,
        operation_type=OperationType.CAPITAL_GAIN,
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
    # SE5 — inventory ledger entries
    # ------------------------------------------------------------------

    def assert_ledger(self, entry_key, entry_type, qty_delta, value_delta, *, count=1):
        """Every matching ledger row has exact deltas (SE5)."""
        qs = ProductLedgerEntry.objects.filter(entry_type=entry_type)
        if isinstance(entry_key, Product):
            qs = qs.filter(product=entry_key)
        elif hasattr(entry_key, "operation_id") and hasattr(entry_key, "product_template"):
            qs = qs.filter(invoice_item=entry_key)
        else:
            raise TypeError("entry_key must be a Product or InvoiceItem")
        self.assertEqual(
            qs.count(), count, f"Expected {count} ledger rows of {entry_type}"
        )
        for entry in qs:
            self.assertEqual(entry.quantity_delta, qty_delta, "ledger quantity_delta")
            self.assertEqual(entry.value_delta, value_delta, "ledger value_delta")

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
    """Net quantity/value per product across the whole ledger (REVERSAL rows
    are included because append-only; net deltas cancel them out)."""
    totals = {}
    rows = (
        ProductLedgerEntry.objects.exclude(product__isnull=True)
        .values("product_id")
        .annotate(qty=Sum("quantity_delta"), value=Sum("value_delta"))
    )
    for row in rows:
        totals[row["product_id"]] = (
            row["qty"] or Decimal("0.00"),
            row["value"] or Decimal("0.00"),
        )
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


# ---------------------------------------------------------------------------
# Phase E — Coverage manifest (executable contract for the section-4 matrix)
# ---------------------------------------------------------------------------
#
# ``COVERAGE_MANIFEST`` declares the canonical test method that pins each
# ``(operation_type, action, side_effect)`` cell of the plan's section-4 matrix.
# The side-effect field is the SE code (SE1..SE12) for the primary cells and a
# free-form qualifier (e.g. ``SE4+reversed_repayment_no_leak``, ``differential``)
# for the extra crown-jewel assertions documented in the plan.
#
# ``CoverageManifestTest`` fails whenever a declared path no longer resolves to
# a real test method (renamed / moved / deleted), so the plan matrix cannot
# silently drift from the suite. When adding a granular test, add it to both
# ``ai-plans/improve-operation-test-suite-plan.md`` and this manifest.
#
# Note: this class is defined here (as the plan specifies) but Django's test
# discovery only scans ``test*.py`` modules, so it is re-exported for discovery
# from ``apps/app_operation/tests/test_coverage_manifest.py``.

_OPS_TESTS = "apps.app_operation.tests.operations"
_ADJ_TESTS = "apps.app_adjustment.tests"
_INV_TESTS = "apps.app_inventory.tests"
_TXN_TESTS = "apps.app_transaction.tests"


def _path(module: str, klass: str, method: str) -> str:
    """Build a ``module:Class.method`` test-path string for the manifest."""
    return f"{module}:{klass}.{method}"


COVERAGE_MANIFEST: dict[tuple[str, str, str], str] = {
    # ------------------------------------------------------------- WORKER_ADVANCE
    ("WORKER_ADVANCE", "create", "SE2"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_create",
        "WorkerAdvanceCreateTest", "test_create_creates_issuance_tx_exact"),
    ("WORKER_ADVANCE", "create", "SE3"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_create",
        "WorkerAdvanceCreateTest", "test_create_project_balance_decreases"),
    ("WORKER_ADVANCE", "create", "SE4"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_create",
        "WorkerAdvanceCreateTest", "test_create_project_receivables_increase"),
    ("WORKER_ADVANCE", "create", "SE8"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_create",
        "WorkerAdvanceCreateTest", "test_create_remaining_to_repay_equals_amount"),
    ("WORKER_ADVANCE", "repay", "SE2"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_repayment",
        "WorkerAdvanceRepaymentTest", "test_repayment_creates_repayment_tx_exact"),
    ("WORKER_ADVANCE", "repay", "SE3"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_repayment",
        "WorkerAdvanceRepaymentTest", "test_worker_fund_decreases_after_repayment"),
    ("WORKER_ADVANCE", "repay", "SE4"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_repayment",
        "WorkerAdvanceRepaymentTest", "test_repayment_decreases_project_receivables"),
    ("WORKER_ADVANCE", "repay", "SE8"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_repayment",
        "WorkerAdvanceRepaymentTest", "test_amount_remaining_to_repay_decreases_after_repayment"),
    ("WORKER_ADVANCE", "repay", "SE4+reversed_repayment_no_leak"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_repayment",
        "WorkerAdvanceRepaymentTest", "test_reversed_repayment_keeps_project_payables_zero"),
    ("WORKER_ADVANCE", "repay", "differential"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_repayment",
        "WorkerAdvanceRepaymentTest", "test_repay_then_reverse_repayment_returns_to_advance_state"),
    ("WORKER_ADVANCE", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_reversal",
        "WorkerAdvanceReversalTest", "test_reverse_creates_reversal_operation"),
    ("WORKER_ADVANCE", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_reversal",
        "WorkerAdvanceReversalTest", "test_reverse_creates_counter_transactions_for_issuance_and_payment"),
    ("WORKER_ADVANCE", "reverse", "SE3"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_reversal",
        "WorkerAdvanceReversalTest", "test_project_fund_restored_after_reversal"),
    ("WORKER_ADVANCE", "reverse", "SE4"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_reversal",
        "WorkerAdvanceReversalTest", "test_reverse_project_receivables_restored"),
    ("WORKER_ADVANCE", "reverse", "SE4+unchanged_buckets"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_reversal",
        "WorkerAdvanceReversalTest", "test_reverse_project_payables_unchanged"),
    ("WORKER_ADVANCE", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_reversal",
        "WorkerAdvanceReversalTest", "test_create_then_reverse_leaves_world_unchanged"),
    ("WORKER_ADVANCE", "reverse", "SE10"): _path(
        f"{_OPS_TESTS}.worker.test_worker_advance_worker_advance_reversal",
        "WorkerAdvanceReversalTest", "test_reversal_blocked_when_repayment_exists"),

    # ---------------------------------------------------------------- PURCHASE
    ("PURCHASE", "create", "SE2"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_create",
        "PurchaseCreateTest", "test_save_creates_exactly_one_issuance_transaction"),
    ("PURCHASE", "create", "SE4"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_create",
        "PurchaseCreateTest", "test_create_project_payables_increase"),
    ("PURCHASE", "create", "SE8"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_create",
        "PurchaseCreateTest", "test_amount_remaining_to_settle_equals_full_amount_after_creation"),
    ("PURCHASE", "create", "SE5"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_create",
        "PurchaseCreateFromSessionTest", "test_create_from_session_ledger_entries_created"),
    ("PURCHASE", "pay", "SE2"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_payment",
        "PurchasePaymentTest", "test_payment_creates_purchase_payment_transaction"),
    ("PURCHASE", "pay", "SE3"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_payment",
        "PurchasePaymentTest", "test_project_fund_decreases_by_payment_amount"),
    ("PURCHASE", "pay", "SE8"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_payment",
        "PurchasePaymentTest", "test_amount_remaining_to_settle_decreases_after_payment"),
    ("PURCHASE", "pay", "SE10"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_payment",
        "PurchasePaymentTest", "test_payment_blocked_when_project_fund_has_insufficient_balance"),
    ("PURCHASE", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_reversal",
        "PurchaseReversalTest", "test_reverse_creates_reversal_operation"),
    ("PURCHASE", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_reversal",
        "PurchaseReversalTest", "test_reverse_creates_counter_transaction_for_issuance"),
    ("PURCHASE", "reverse", "SE4"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_reversal",
        "PurchaseReversalTest", "test_reverse_restores_project_payables"),
    ("PURCHASE", "reverse", "SE4+unchanged_buckets"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_reversal",
        "PurchaseReversalTest", "test_reverse_project_receivables_unchanged"),
    ("PURCHASE", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_reversal",
        "PurchaseReversalTest", "test_create_then_reverse_leaves_world_unchanged"),
    ("PURCHASE", "reverse", "SE10"): _path(
        f"{_OPS_TESTS}.purchase.test_purchase_reversal",
        "PurchaseReversalTest", "test_reversal_blocked_when_payment_exists"),
    ("PURCHASE", "move", "SE5"): _path(
        f"{_INV_TESTS}.test_inventory_movement",
        "InventoryMovementCreationTest", "test_create_inventory_movement_purchase"),
    ("PURCHASE", "move", "SE6"): _path(
        f"{_INV_TESTS}.test_inventory_movement",
        "InventoryMovementCreationTest", "test_create_inventory_movement_purchase"),
    ("PURCHASE", "move", "SE7"): _path(
        f"{_INV_TESTS}.test_inventory_movement",
        "InventoryMovementCreationTest", "test_create_inventory_movement_purchase"),

    # ------------------------------------------------------------------ SALE
    ("SALE", "create", "SE2"): _path(
        f"{_OPS_TESTS}.sale.test_sale_sale_create",
        "SaleCreateTest", "test_save_creates_exactly_one_issuance_transaction"),
    ("SALE", "create", "SE4"): _path(
        f"{_OPS_TESTS}.sale.test_sale_sale_create",
        "SaleCreateTest", "test_create_project_receivables_increase"),
    ("SALE", "create", "SE8"): _path(
        f"{_OPS_TESTS}.sale.test_sale_sale_create",
        "SaleCreateTest", "test_amount_remaining_to_settle_equals_full_amount_after_creation"),
    ("SALE", "pay", "SE2"): _path(
        f"{_OPS_TESTS}.sale.test_sale_sale_collection",
        "SaleCollectionTest", "test_collection_creates_sale_collection_transaction"),
    ("SALE", "pay", "SE3"): _path(
        f"{_OPS_TESTS}.sale.test_sale_sale_collection",
        "SaleCollectionTest", "test_project_fund_increases_by_collection_amount"),
    ("SALE", "pay", "SE8"): _path(
        f"{_OPS_TESTS}.sale.test_sale_sale_collection",
        "SaleCollectionTest", "test_amount_remaining_to_settle_decreases_after_collection"),
    ("SALE", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.sale.test_sale_sale_reversal",
        "SaleReversalTest", "test_reverse_creates_reversal_operation"),
    ("SALE", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.sale.test_sale_sale_reversal",
        "SaleReversalTest", "test_reverse_creates_counter_transaction_for_issuance"),
    ("SALE", "reverse", "SE4"): _path(
        f"{_OPS_TESTS}.sale.test_sale_sale_reversal",
        "SaleReversalTest", "test_reverse_restores_project_receivables"),
    ("SALE", "reverse", "SE7"): _path(
        f"{_OPS_TESTS}.sale.test_sale_sale_reversal",
        "SaleReversalProductStatusRestorationTest", "test_reverse_restores_sold_product_to_active"),
    ("SALE", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.sale.test_sale_sale_reversal",
        "SaleReversalTest", "test_create_then_reverse_leaves_world_unchanged"),
    ("SALE", "reverse", "SE10"): _path(
        f"{_OPS_TESTS}.sale.test_sale_sale_reversal",
        "SaleReversalTest", "test_reversal_blocked_when_collection_exists"),
    ("SALE", "move", "SE5"): _path(
        f"{_INV_TESTS}.test_inventory_movement",
        "InventoryMovementCreationTest", "test_sale_operation_movement"),

    # ---------------------------------------------------------------- EXPENSE
    ("EXPENSE", "create", "SE2"): _path(
        f"{_OPS_TESTS}.expense.test_expense_expense_create",
        "ExpenseCreateTest", "test_save_creates_exactly_one_issuance_transaction"),
    ("EXPENSE", "create", "SE4"): _path(
        f"{_OPS_TESTS}.expense.test_expense_expense_create",
        "ExpenseCreateTest", "test_create_project_payables_increase"),
    ("EXPENSE", "create", "SE8"): _path(
        f"{_OPS_TESTS}.expense.test_expense_expense_create",
        "ExpenseCreateTest", "test_amount_remaining_to_settle_equals_full_amount_after_creation"),
    ("EXPENSE", "pay", "SE2"): _path(
        f"{_OPS_TESTS}.expense.test_expense_expense_payment",
        "ExpensePaymentTest", "test_payment_creates_expense_payment_transaction"),
    ("EXPENSE", "pay", "SE3"): _path(
        f"{_OPS_TESTS}.expense.test_expense_expense_payment",
        "ExpensePaymentTest", "test_project_fund_decreases_by_payment_amount"),
    ("EXPENSE", "pay", "SE8"): _path(
        f"{_OPS_TESTS}.expense.test_expense_expense_payment",
        "ExpensePaymentTest", "test_amount_remaining_to_settle_decreases_after_payment"),
    ("EXPENSE", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.expense.test_expense_expense_reversal",
        "ExpenseReversalTest", "test_reverse_creates_reversal_operation"),
    ("EXPENSE", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.expense.test_expense_expense_reversal",
        "ExpenseReversalTest", "test_reverse_creates_counter_transaction_for_issuance"),
    ("EXPENSE", "reverse", "SE4"): _path(
        f"{_OPS_TESTS}.expense.test_expense_expense_reversal",
        "ExpenseReversalTest", "test_reverse_restores_project_payables"),
    ("EXPENSE", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.expense.test_expense_expense_reversal",
        "ExpenseReversalTest", "test_create_then_reverse_leaves_world_unchanged"),
    ("EXPENSE", "reverse", "SE10"): _path(
        f"{_OPS_TESTS}.expense.test_expense_expense_reversal",
        "ExpenseReversalTest", "test_reversal_blocked_when_payment_exists"),

    # ------------------------------------------------------------------- LOAN
    ("LOAN", "create", "SE2"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_create",
        "LoanCreateTest", "test_creates_issuance_transaction_on_save"),
    ("LOAN", "create", "SE8"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_create",
        "LoanCreateTest", "test_amount_remaining_to_repay_equals_issuance_amount_initially"),
    ("LOAN", "pay", "SE2"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_disbursement",
        "LoanDisbursementTest", "test_payment_creates_loan_payment_transaction"),
    ("LOAN", "pay", "SE3"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_disbursement",
        "LoanDisbursementTest", "test_creditor_fund_decreases_after_payment"),
    ("LOAN", "pay", "SE4"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_disbursement",
        "LoanDisbursementTest", "test_payment_increases_debtor_payables"),
    ("LOAN", "repay", "SE2"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_repayment",
        "LoanRepaymentTest", "test_repayment_creates_loan_repayment_transaction"),
    ("LOAN", "repay", "SE3"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_repayment",
        "LoanRepaymentTest", "test_debtor_fund_decreases_after_repayment"),
    ("LOAN", "repay", "SE4"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_repayment",
        "LoanRepaymentTest", "test_repayment_decreases_debtor_payables"),
    ("LOAN", "repay", "SE4+no_disbursement_negative"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_repayment",
        "LoanRepaymentTest", "test_repayment_without_disbursement_drives_obligations_negative"),
    ("LOAN", "repay", "SE8"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_repayment",
        "LoanRepaymentTest", "test_amount_remaining_to_repay_decreases_after_repayment"),
    ("LOAN", "repay", "differential"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_repayment",
        "LoanRepaymentTest", "test_repay_then_reverse_repayment_returns_to_advance_state"),
    ("LOAN", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_reversal",
        "LoanReversalTest", "test_reverse_creates_reversal_operation"),
    ("LOAN", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_reversal",
        "LoanReversalTest", "test_reverse_creates_counter_issuance_transaction"),
    ("LOAN", "reverse", "SE4"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_reversal",
        "LoanReversalTest", "test_reverse_issuance_leaves_obligations_zero"),
    ("LOAN", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_reversal",
        "LoanReversalTest", "test_create_then_reverse_leaves_world_unchanged"),
    ("LOAN", "reverse", "SE10"): _path(
        f"{_OPS_TESTS}.loan.test_loan_loan_reversal",
        "LoanReversalTest", "test_reversal_blocked_when_payment_disbursement_exists"),

    # ------------------------------------------------------------------ BIRTH
    ("BIRTH", "create", "SE2"): _path(
        f"{_OPS_TESTS}.birth.test_birth_birth_create",
        "BirthCreateTest", "test_save_creates_issuance_and_payment_transactions"),
    ("BIRTH", "create", "SE5"): _path(
        f"{_OPS_TESTS}.birth.test_birth_birth_create",
        "BirthCreateTest", "test_create_writes_movement_and_issuance_ledger_entries"),
    ("BIRTH", "create", "SE6"): _path(
        f"{_OPS_TESTS}.birth.test_birth_birth_create",
        "BirthCreateTest", "test_create_auto_creates_inbound_movement_lines"),
    ("BIRTH", "create", "SE7"): _path(
        f"{_OPS_TESTS}.birth.test_birth_birth_create",
        "BirthCreateTest", "test_created_product_is_active"),
    ("BIRTH", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.birth.test_birth_birth_reversal",
        "BirthReversalTest", "test_reverse_creates_reversal_record"),
    ("BIRTH", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.birth.test_birth_birth_reversal",
        "BirthReversalTest", "test_reverse_creates_counter_transactions"),
    ("BIRTH", "reverse", "SE5"): _path(
        f"{_OPS_TESTS}.birth.test_birth_birth_reversal",
        "BirthReversalTest", "test_reverse_movement_ledger_negation_exact_set"),
    ("BIRTH", "reverse", "SE6"): _path(
        f"{_OPS_TESTS}.birth.test_birth_birth_reversal",
        "BirthReversalTest", "test_reverse_reverses_auto_movement_lines"),
    ("BIRTH", "reverse", "SE7"): _path(
        f"{_OPS_TESTS}.birth.test_birth_birth_reversal",
        "BirthReversalTest", "test_reverse_born_products_removed_from_stock"),
    ("BIRTH", "reverse", "SE10"): _path(
        f"{_OPS_TESTS}.birth.test_birth_birth_reversal",
        "BirthReversalTest", "test_cannot_reverse_already_reversed_operation"),

    # ------------------------------------------------------------------ DEATH
    ("DEATH", "create", "SE2"): _path(
        f"{_OPS_TESTS}.inventory.test_death_death_create",
        "DeathCreateTest", "test_save_creates_issuance_and_payment_transactions"),
    ("DEATH", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.inventory.test_death_death_reversal",
        "DeathReversalTest", "test_reverse_creates_reversal_record"),
    ("DEATH", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.inventory.test_death_death_reversal",
        "DeathReversalTest", "test_reverse_creates_counter_transactions"),
    ("DEATH", "reverse", "SE5"): _path(
        f"{_OPS_TESTS}.inventory.test_death_death_reversal",
        "DeathReversalTest", "test_reverse_movement_ledger_negation_exact_set"),
    ("DEATH", "reverse", "SE6"): _path(
        f"{_OPS_TESTS}.inventory.test_death_death_reversal",
        "DeathReversalTest", "test_reverse_reverses_auto_movement_lines"),
    ("DEATH", "reverse", "SE7"): _path(
        f"{_OPS_TESTS}.inventory.test_death_death_reversal",
        "DeathReversalTest", "test_reversed_product_returns_to_active_status"),
    ("DEATH", "reverse", "SE10"): _path(
        f"{_OPS_TESTS}.inventory.test_death_death_reversal",
        "DeathReversalTest", "test_cannot_reverse_already_reversed_operation"),

    # ------------------------------------------------------------ CONSUMPTION
    ("CONSUMPTION", "create", "SE2"): _path(
        f"{_OPS_TESTS}.inventory.test_consumption_consumption_create",
        "ConsumptionCreateTest", "test_create_creates_issuance_and_payment_transactions"),
    ("CONSUMPTION", "create", "SE5"): _path(
        f"{_OPS_TESTS}.inventory.test_consumption_consumption_create",
        "ConsumptionCreateTest", "test_create_writes_movement_and_issuance_ledger_entries"),
    ("CONSUMPTION", "create", "SE6"): _path(
        f"{_OPS_TESTS}.inventory.test_consumption_consumption_create",
        "ConsumptionCreateTest", "test_create_auto_creates_movement_line"),
    ("CONSUMPTION", "create", "SE7"): _path(
        f"{_OPS_TESTS}.inventory.test_consumption_consumption_create",
        "ConsumptionCreateTest", "test_create_marks_product_consumed"),
    ("CONSUMPTION", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.inventory.test_consumption_consumption_reversal",
        "ConsumptionReversalTest", "test_reverse_creates_reversal_record"),
    ("CONSUMPTION", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.inventory.test_consumption_consumption_reversal",
        "ConsumptionReversalTest", "test_reverse_creates_counter_transactions"),
    ("CONSUMPTION", "reverse", "SE5"): _path(
        f"{_OPS_TESTS}.inventory.test_consumption_consumption_reversal",
        "ConsumptionReversalTest", "test_reverse_movement_ledger_negation_exact_set"),
    ("CONSUMPTION", "reverse", "SE6"): _path(
        f"{_OPS_TESTS}.inventory.test_consumption_consumption_reversal",
        "ConsumptionReversalTest", "test_reverse_reverses_auto_movement_lines"),
    ("CONSUMPTION", "reverse", "SE7"): _path(
        f"{_OPS_TESTS}.inventory.test_consumption_consumption_reversal",
        "ConsumptionReversalTest", "test_reversed_product_returns_to_active_status"),

    # ------------------------------------------------------------ CAPITAL_GAIN
    ("CAPITAL_GAIN", "create", "SE2"): _path(
        f"{_OPS_TESTS}.capital.test_capital_gain_capital_gain_create",
        "CapitalGainCreateTest", "test_creates_issuance_and_payment_transactions"),
    ("CAPITAL_GAIN", "create", "SE3"): _path(
        f"{_OPS_TESTS}.capital.test_capital_gain_capital_gain_create",
        "CapitalGainCreateTest", "test_project_fund_increases_by_gain_amount"),
    ("CAPITAL_GAIN", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.capital.test_capital_gain_capital_gain_reversal",
        "CapitalGainReversalTest", "test_reverse_creates_reversal_operation"),
    ("CAPITAL_GAIN", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.capital.test_capital_gain_capital_gain_reversal",
        "CapitalGainReversalTest", "test_reverse_creates_counter_transactions"),
    ("CAPITAL_GAIN", "reverse", "SE3"): _path(
        f"{_OPS_TESTS}.capital.test_capital_gain_capital_gain_reversal",
        "CapitalGainReversalTest", "test_project_fund_restored_after_reversal"),
    ("CAPITAL_GAIN", "reverse", "SE7"): _path(
        f"{_OPS_TESTS}.capital.test_capital_gain_capital_gain_reversal",
        "CapitalGainReversalProductStatusTest", "test_gain_and_reversal_keep_product_active"),
    ("CAPITAL_GAIN", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.capital.test_capital_gain_capital_gain_reversal",
        "CapitalGainReversalTest", "test_create_then_reverse_leaves_world_unchanged"),

    # ------------------------------------------------------------ CAPITAL_LOSS
    ("CAPITAL_LOSS", "create", "SE2"): _path(
        f"{_OPS_TESTS}.capital.test_capital_loss_capital_loss_create",
        "CapitalLossCreateTest", "test_creates_issuance_and_payment_transactions"),
    ("CAPITAL_LOSS", "create", "SE3"): _path(
        f"{_OPS_TESTS}.capital.test_capital_loss_capital_loss_create",
        "CapitalLossCreateTest", "test_project_fund_decreases_by_loss_amount"),
    ("CAPITAL_LOSS", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.capital.test_capital_loss_capital_loss_reversal",
        "CapitalLossReversalTest", "test_reverse_creates_reversal_operation"),
    ("CAPITAL_LOSS", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.capital.test_capital_loss_capital_loss_reversal",
        "CapitalLossReversalTest", "test_reverse_creates_counter_transactions"),
    ("CAPITAL_LOSS", "reverse", "SE3"): _path(
        f"{_OPS_TESTS}.capital.test_capital_loss_capital_loss_reversal",
        "CapitalLossReversalTest", "test_project_fund_restored_after_reversal"),
    ("CAPITAL_LOSS", "reverse", "SE7"): _path(
        f"{_OPS_TESTS}.capital.test_capital_loss_capital_loss_reversal",
        "CapitalLossReversalProductStatusTest", "test_loss_and_reversal_keep_product_active"),
    ("CAPITAL_LOSS", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.capital.test_capital_loss_capital_loss_reversal",
        "CapitalLossReversalTest", "test_create_then_reverse_leaves_world_unchanged"),

    # ---------------------------------------------------------- CASH_INJECTION
    ("CASH_INJECTION", "create", "SE2"): _path(
        f"{_OPS_TESTS}.cash.test_cash_injection_cash_injection_create",
        "CashInjectionCreateTest", "test_creates_issuance_and_payment_transactions"),
    ("CASH_INJECTION", "create", "SE3"): _path(
        f"{_OPS_TESTS}.cash.test_cash_injection_cash_injection_create",
        "CashInjectionCreateTest", "test_receiver_balance_increases_after_cash_injection"),
    ("CASH_INJECTION", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.cash.test_cash_injection_cash_injection_reversal",
        "CashInjectionReversalTest", "test_reverse_creates_reversal_operation"),
    ("CASH_INJECTION", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.cash.test_cash_injection_cash_injection_reversal",
        "CashInjectionReversalTest", "test_reverse_creates_counter_transactions"),
    ("CASH_INJECTION", "reverse", "SE3"): _path(
        f"{_OPS_TESTS}.cash.test_cash_injection_cash_injection_reversal",
        "CashInjectionReversalTest", "test_receiver_balance_restored_to_zero_after_reversal"),
    ("CASH_INJECTION", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.cash.test_cash_injection_cash_injection_reversal",
        "CashInjectionReversalTest", "test_create_then_reverse_leaves_world_unchanged"),

    # ---------------------------------------------------------- CASH_WITHDRAWAL
    ("CASH_WITHDRAWAL", "create", "SE2"): _path(
        f"{_OPS_TESTS}.cash.test_cash_withdrawal_cash_withdrawal_create",
        "CashWithdrawalCreateTest", "test_creates_issuance_and_payment_transactions"),
    ("CASH_WITHDRAWAL", "create", "SE3"): _path(
        f"{_OPS_TESTS}.cash.test_cash_withdrawal_cash_withdrawal_create",
        "CashWithdrawalCreateTest", "test_withdrawer_balance_decreases_after_withdrawal"),
    ("CASH_WITHDRAWAL", "create", "SE10"): _path(
        f"{_OPS_TESTS}.cash.test_cash_withdrawal_cash_withdrawal_create",
        "CashWithdrawalCreateTest", "test_insufficient_funds_blocked"),
    ("CASH_WITHDRAWAL", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.cash.test_cash_withdrawal_cash_withdrawal_reversal",
        "CashWithdrawalReversalTest", "test_reverse_creates_reversal_operation"),
    ("CASH_WITHDRAWAL", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.cash.test_cash_withdrawal_cash_withdrawal_reversal",
        "CashWithdrawalReversalTest", "test_reverse_creates_counter_transactions"),
    ("CASH_WITHDRAWAL", "reverse", "SE3"): _path(
        f"{_OPS_TESTS}.cash.test_cash_withdrawal_cash_withdrawal_reversal",
        "CashWithdrawalReversalTest", "test_withdrawer_balance_restored_after_reversal"),
    ("CASH_WITHDRAWAL", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.cash.test_cash_withdrawal_cash_withdrawal_reversal",
        "CashWithdrawalReversalTest", "test_create_then_reverse_leaves_world_unchanged"),

    # ---------------------------------------------------------- PROJECT_FUNDING
    ("PROJECT_FUNDING", "create", "SE2"): _path(
        f"{_OPS_TESTS}.funding.test_project_funding_project_funding_create",
        "ProjectFundingCreateTest", "test_creates_issuance_and_payment_transactions"),
    ("PROJECT_FUNDING", "create", "SE3"): _path(
        f"{_OPS_TESTS}.funding.test_project_funding_project_funding_create",
        "ProjectFundingCreateTest", "test_project_fund_increases_after_funding"),
    ("PROJECT_FUNDING", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.funding.test_project_funding_project_funding_reversal",
        "ProjectFundingReversalTest", "test_reverse_creates_reversal_operation"),
    ("PROJECT_FUNDING", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.funding.test_project_funding_project_funding_reversal",
        "ProjectFundingReversalTest", "test_reverse_creates_counter_transactions"),
    ("PROJECT_FUNDING", "reverse", "SE3"): _path(
        f"{_OPS_TESTS}.funding.test_project_funding_project_funding_reversal",
        "ProjectFundingReversalTest", "test_project_fund_restored_after_reversal"),
    ("PROJECT_FUNDING", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.funding.test_project_funding_project_funding_reversal",
        "ProjectFundingReversalTest", "test_create_then_reverse_leaves_world_unchanged"),

    # ------------------------------------------------------------ PROJECT_REFUND
    ("PROJECT_REFUND", "create", "SE2"): _path(
        f"{_OPS_TESTS}.funding.test_project_refund_project_refund_create",
        "ProjectRefundCreateTest", "test_creates_issuance_and_payment_transactions"),
    ("PROJECT_REFUND", "create", "SE3"): _path(
        f"{_OPS_TESTS}.funding.test_project_refund_project_refund_create",
        "ProjectRefundCreateTest", "test_project_fund_decreases_after_refund"),
    ("PROJECT_REFUND", "create", "SE4"): _path(
        f"{_OPS_TESTS}.funding.test_project_refund_project_refund_create",
        "ProjectRefundCreateTest", "test_create_leaves_payables_receivables_zero"),
    ("PROJECT_REFUND", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.funding.test_project_refund_project_refund_reversal",
        "ProjectRefundReversalTest", "test_reverse_creates_reversal_operation"),
    ("PROJECT_REFUND", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.funding.test_project_refund_project_refund_reversal",
        "ProjectRefundReversalTest", "test_reverse_creates_counter_transactions"),
    ("PROJECT_REFUND", "reverse", "SE3"): _path(
        f"{_OPS_TESTS}.funding.test_project_refund_project_refund_reversal",
        "ProjectRefundReversalTest", "test_project_fund_restored_after_reversal"),
    ("PROJECT_REFUND", "reverse", "SE4"): _path(
        f"{_OPS_TESTS}.funding.test_project_refund_project_refund_reversal",
        "ProjectRefundReversalTest", "test_reverse_leaves_payables_receivables_zero"),
    ("PROJECT_REFUND", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.funding.test_project_refund_project_refund_reversal",
        "ProjectRefundReversalTest", "test_create_then_reverse_leaves_world_unchanged"),

    # -------------------------------------------------------- PROFIT_DISTRIBUTION
    ("PROFIT_DISTRIBUTION", "create", "SE2"): _path(
        f"{_OPS_TESTS}.distribution.test_profit_distribution_profit_distribution_create",
        "ProfitDistributionCreateTest", "test_creates_issuance_and_payment_transactions"),
    ("PROFIT_DISTRIBUTION", "create", "SE3"): _path(
        f"{_OPS_TESTS}.distribution.test_profit_distribution_profit_distribution_create",
        "ProfitDistributionCreateTest", "test_project_fund_decreases_by_distribution_amount"),
    ("PROFIT_DISTRIBUTION", "create", "SE4"): _path(
        f"{_OPS_TESTS}.distribution.test_profit_distribution_profit_distribution_create",
        "ProfitDistributionCreateTest", "test_create_leaves_payables_receivables_zero"),
    ("PROFIT_DISTRIBUTION", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.distribution.test_profit_distribution_profit_distribution_reversal",
        "ProfitDistributionReversalTest", "test_reverse_creates_reversal_operation"),
    ("PROFIT_DISTRIBUTION", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.distribution.test_profit_distribution_profit_distribution_reversal",
        "ProfitDistributionReversalTest", "test_reverse_creates_counter_transactions"),
    ("PROFIT_DISTRIBUTION", "reverse", "SE3"): _path(
        f"{_OPS_TESTS}.distribution.test_profit_distribution_profit_distribution_reversal",
        "ProfitDistributionReversalTest", "test_project_fund_restored_after_reversal"),
    ("PROFIT_DISTRIBUTION", "reverse", "SE4"): _path(
        f"{_OPS_TESTS}.distribution.test_profit_distribution_profit_distribution_reversal",
        "ProfitDistributionReversalTest", "test_reverse_leaves_payables_receivables_zero"),
    ("PROFIT_DISTRIBUTION", "reverse", "SE8"): _path(
        f"{_OPS_TESTS}.distribution.test_profit_distribution_profit_distribution_reversal",
        "ProfitDistributionReversalTest", "test_reversal_restores_remaining_distributable"),
    ("PROFIT_DISTRIBUTION", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.distribution.test_profit_distribution_profit_distribution_reversal",
        "ProfitDistributionReversalTest", "test_create_then_reverse_leaves_world_unchanged"),

    # ------------------------------------------------------------- LOSS_COVERAGE
    ("LOSS_COVERAGE", "create", "SE2"): _path(
        f"{_OPS_TESTS}.distribution.test_loss_coverage_loss_coverage_create",
        "LossCoverageCreateTest", "test_creates_issuance_and_payment_transactions"),
    ("LOSS_COVERAGE", "create", "SE3"): _path(
        f"{_OPS_TESTS}.distribution.test_loss_coverage_loss_coverage_create",
        "LossCoverageCreateTest", "test_shareholder_fund_decreases_by_coverage_amount"),
    ("LOSS_COVERAGE", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.distribution.test_loss_coverage_loss_coverage_reversal",
        "LossCoverageReversalTest", "test_reverse_creates_reversal_operation"),
    ("LOSS_COVERAGE", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.distribution.test_loss_coverage_loss_coverage_reversal",
        "LossCoverageReversalTest", "test_reverse_creates_counter_transactions"),
    ("LOSS_COVERAGE", "reverse", "SE3"): _path(
        f"{_OPS_TESTS}.distribution.test_loss_coverage_loss_coverage_reversal",
        "LossCoverageReversalTest", "test_shareholder_fund_restored_after_reversal"),
    ("LOSS_COVERAGE", "reverse", "SE8"): _path(
        f"{_OPS_TESTS}.distribution.test_loss_coverage_loss_coverage_reversal",
        "LossCoverageReversalTest", "test_reversal_restores_remaining_coverable"),
    ("LOSS_COVERAGE", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.distribution.test_loss_coverage_loss_coverage_reversal",
        "LossCoverageReversalTest", "test_create_then_reverse_leaves_world_unchanged"),

    # ---------------------------------------------------------- INTERNAL_TRANSFER
    ("INTERNAL_TRANSFER", "create", "SE2"): _path(
        f"{_OPS_TESTS}.transfer.test_internal_transfer_internal_transfer_create",
        "InternalTransferCreateTest", "test_creates_issuance_and_payment_transactions"),
    ("INTERNAL_TRANSFER", "create", "SE3"): _path(
        f"{_OPS_TESTS}.transfer.test_internal_transfer_internal_transfer_create",
        "InternalTransferCreateTest", "test_source_balance_decreases_after_transfer"),
    ("INTERNAL_TRANSFER", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.transfer.test_internal_transfer_internal_transfer_reversal",
        "InternalTransferReversalTest", "test_reverse_creates_reversal_operation"),
    ("INTERNAL_TRANSFER", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.transfer.test_internal_transfer_internal_transfer_reversal",
        "InternalTransferReversalTest", "test_reverse_creates_counter_transactions"),
    ("INTERNAL_TRANSFER", "reverse", "SE3"): _path(
        f"{_OPS_TESTS}.transfer.test_internal_transfer_internal_transfer_reversal",
        "InternalTransferReversalTest", "test_source_balance_restored_after_reversal"),
    ("INTERNAL_TRANSFER", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.transfer.test_internal_transfer_internal_transfer_reversal",
        "InternalTransferReversalTest", "test_create_then_reverse_leaves_world_unchanged"),

    # ---------------------------------------------------------- CORRECTION_CREDIT
    ("CORRECTION_CREDIT", "create", "SE2"): _path(
        f"{_OPS_TESTS}.corrections.test_correction_correction_credit_create",
        "CorrectionCreditCreateTest", "test_creates_issuance_and_payment_transactions"),
    ("CORRECTION_CREDIT", "create", "SE3"): _path(
        f"{_OPS_TESTS}.corrections.test_correction_correction_credit_create",
        "CorrectionCreditCreateTest", "test_project_fund_increases_by_correction_amount"),
    ("CORRECTION_CREDIT", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.corrections.test_correction_correction_credit_reversal",
        "CorrectionCreditReversalTest", "test_reverse_creates_reversal_operation"),
    ("CORRECTION_CREDIT", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.corrections.test_correction_correction_credit_reversal",
        "CorrectionCreditReversalTest", "test_reverse_creates_counter_transactions"),
    ("CORRECTION_CREDIT", "reverse", "SE3"): _path(
        f"{_OPS_TESTS}.corrections.test_correction_correction_credit_reversal",
        "CorrectionCreditReversalTest", "test_project_fund_restored_after_reversal"),
    ("CORRECTION_CREDIT", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.corrections.test_correction_correction_credit_reversal",
        "CorrectionCreditReversalTest", "test_create_then_reverse_leaves_world_unchanged"),

    # ----------------------------------------------------------- CORRECTION_DEBIT
    ("CORRECTION_DEBIT", "create", "SE2"): _path(
        f"{_OPS_TESTS}.corrections.test_correction_correction_debit_create",
        "CorrectionDebitCreateTest", "test_creates_issuance_and_payment_transactions"),
    ("CORRECTION_DEBIT", "create", "SE3"): _path(
        f"{_OPS_TESTS}.corrections.test_correction_correction_debit_create",
        "CorrectionDebitCreateTest", "test_project_fund_decreases_by_correction_amount"),
    ("CORRECTION_DEBIT", "reverse", "SE1"): _path(
        f"{_OPS_TESTS}.corrections.test_correction_correction_debit_reversal",
        "CorrectionDebitReversalTest", "test_reverse_creates_reversal_operation"),
    ("CORRECTION_DEBIT", "reverse", "SE2"): _path(
        f"{_OPS_TESTS}.corrections.test_correction_correction_debit_reversal",
        "CorrectionDebitReversalTest", "test_reverse_creates_counter_transactions"),
    ("CORRECTION_DEBIT", "reverse", "SE3"): _path(
        f"{_OPS_TESTS}.corrections.test_correction_correction_debit_reversal",
        "CorrectionDebitReversalTest", "test_project_fund_restored_after_reversal"),
    ("CORRECTION_DEBIT", "reverse", "differential"): _path(
        f"{_OPS_TESTS}.corrections.test_correction_correction_debit_reversal",
        "CorrectionDebitReversalTest", "test_create_then_reverse_leaves_world_unchanged"),

    # --------------------------------------------------------- ADJUST (PURCHASE/SALE/EXPENSE)
    ("PURCHASE", "adjust", "SE2"): _path(
        f"{_ADJ_TESTS}.test_adjustment_adjustment_transaction",
        "AdjustmentTransactionTest", "test_purchase_adjustment_creates_purchase_adjustment_transaction"),
    ("SALE", "adjust", "SE2"): _path(
        f"{_ADJ_TESTS}.test_adjustment_adjustment_transaction",
        "AdjustmentTransactionTest", "test_sale_adjustment_creates_sale_adjustment_transaction"),
    ("EXPENSE", "adjust", "SE2"): _path(
        f"{_ADJ_TESTS}.test_adjustment_adjustment_transaction",
        "AdjustmentTransactionTest", "test_expense_adjustment_creates_expense_adjustment_transaction"),
    ("PURCHASE", "adjust", "SE4"): _path(
        f"{_ADJ_TESTS}.test_adjustment_adjustment_reversal",
        "AdjustmentReversalTest", "test_purchase_return_reduces_project_payables"),
    ("PURCHASE", "adjust", "SE5"): _path(
        f"{_ADJ_TESTS}.test_invoice_item_adjustment_ledger_entry",
        "LedgerEntryTest", "test_purchase_price_decrease_ledger_entry"),
    ("PURCHASE", "adjust", "SE8"): _path(
        f"{_ADJ_TESTS}.test_adjustment_adjustment_effective_amount",
        "AdjustmentEffectiveAmountTest", "test_single_decrease_reduces_effective_amount"),
    ("PURCHASE", "adjust", "SE11"): _path(
        f"{_ADJ_TESTS}.test_invoice_item_adjustment_ledger_entry",
        "LedgerEntryTest", "test_idempotency_key_prevents_duplicate_entries"),
    ("PURCHASE", "adjust", "reverse_SE4"): _path(
        f"{_ADJ_TESTS}.test_adjustment_adjustment_reversal",
        "AdjustmentReversalTest", "test_reverse_adjustment_restores_project_payables"),
    ("PURCHASE", "adjust", "reverse_SE5"): _path(
        f"{_ADJ_TESTS}.test_invoice_item_adjustment_reversal",
        "ReversalTest", "test_reversal_creates_negating_ledger_entry"),
    ("PURCHASE", "adjust", "reverse_SE8"): _path(
        f"{_ADJ_TESTS}.test_invoice_item_adjustment_reversal",
        "ReversalTest", "test_reversal_restores_effective_amount"),

    # ---------------------------------------------------------- Transaction model
    ("*", "reverse", "SE10"): _path(
        f"{_TXN_TESTS}",
        "TransactionReversalTests", "test_reverse_creates_reversal_transaction"),
    ("*", "reverse", "SE2"): _path(
        f"{_TXN_TESTS}",
        "TransactionReversalTests", "test_reversal_swaps_source_and_target"),
    ("WORKER_ADVANCE", "repay", "SE4"): _path(
        f"{_TXN_TESTS}",
        "EntityObligationRepaymentReversalTests", "test_reversed_repayment_does_not_create_phantom_payables"),
    ("CAPITAL_GAIN", "create", "SE2+auto"): _path(
        f"{_TXN_TESTS}",
        "TransactionAutoCreationTests", "test_capital_gain_creates_issuance_transaction"),
}


def _test_method_exists(path: str) -> bool:
    """True if ``path`` (``module:Class.method``) resolves to a real test method."""
    try:
        module_path, _, class_and_method = path.partition(":")
        class_name, _, method_name = class_and_method.rpartition(".")
        if not class_name or not method_name:
            return False
        module = importlib.import_module(module_path)
        return callable(getattr(getattr(module, class_name), method_name, None))
    except (ImportError, AttributeError):
        return False


class CoverageManifestTest(TestCase):
    """Phase E — makes the declared coverage manifest executable.

    ``COVERAGE_MANIFEST`` declares one canonical test method per
    ``(operation_type, action, side_effect)`` cell of the plan's section-4
    matrix. This test fails whenever a declared path no longer resolves to a
    real test method (renamed / moved / deleted), so the matrix cannot silently
    drift from the suite. When a granular test is added, register it in both the
    plan matrix and this manifest.
    """

    def test_declared_manifest_methods_exist(self):
        missing = [
            (key, path)
            for key, path in COVERAGE_MANIFEST.items()
            if not _test_method_exists(path)
        ]
        if missing:
            details = "\n".join(
                f"  {key} -> {path}" for key, path in sorted(missing)
            )
            self.fail(f"Coverage manifest references missing test methods:\n{details}")
