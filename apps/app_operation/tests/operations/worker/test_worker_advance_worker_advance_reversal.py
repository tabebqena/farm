from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.app_transaction.transaction_type import TransactionType

from apps.app_operation.tests.base import (
    BaseOperationTestCase,
    make_worker,
    make_worker_advance,
)

AMOUNT = Decimal("1000.00")


class WorkerAdvanceReversalTest(BaseOperationTestCase):
    """
    Operation reversal: reversal record, counter-transactions, and restored
    balances / payables / receivables.

    Reversal is only allowed when no repayments exist. Both the issuance and
    payment transactions are implicitly reversed (counter-transactions created
    automatically).
    """

    def setUp(self):
        super().setUp()
        self.worker = make_worker(self.project, "Ali Worker")
        self.op = make_worker_advance(
            self.project, self.worker, self.officer, AMOUNT
        )

    def _reversal(self):
        return self.op.reverse(officer=self.officer)

    # ------------------------------------------------------------------
    # SE1 — reversal record
    # ------------------------------------------------------------------

    def test_reverse_creates_reversal_operation(self):
        reversal = self._reversal()

        self.assertIsNotNone(reversal.pk)
        self.assertEqual(reversal.reversal_of, self.op)

    def test_reverse_marks_original_as_reversed(self):
        reversal = self._reversal()

        self.op.refresh_from_db()
        self.assertTrue(self.op.is_reversed)
        self.assertEqual(self.op.reversed_by, reversal)

    def test_reversal_is_marked_as_reversal(self):
        reversal = self._reversal()

        self.assertTrue(reversal.is_reversal)
        self.assertFalse(reversal.is_reversed)

    def test_reverse_inherits_amount_source_destination(self):
        reversal = self._reversal()

        self.assertEqual(reversal.amount, self.op.amount)
        self.assertEqual(reversal.source, self.op.source)
        self.assertEqual(reversal.destination, self.op.destination)

    # ------------------------------------------------------------------
    # SE2 — counter-transactions
    # ------------------------------------------------------------------

    def test_reverse_creates_counter_transactions_for_issuance_and_payment(self):
        self._reversal()

        # 2 original (issuance + payment) + 2 counter-transactions
        self.assert_tx_types(
            self.op,
            {
                TransactionType.WORKER_ADVANCE_ISSUANCE: 2,
                TransactionType.WORKER_ADVANCE_PAYMENT: 2,
            },
        )

    def test_reverse_counter_transactions_flip_funds(self):
        self._reversal()

        originals = self.op.get_all_transactions().filter(reversal_of__isnull=True)
        self.assertEqual(originals.count(), 2)
        for tx in originals:
            self.assert_counter_tx(tx)

    # ------------------------------------------------------------------
    # SE3 — fund balances restored
    # ------------------------------------------------------------------

    def test_project_fund_restored_after_reversal(self):
        self._reversal()

        self.assert_balance(self.project, self.project_funding, msg="project")

    def test_worker_fund_restored_after_reversal(self):
        self._reversal()

        self.assert_balance(self.worker, Decimal("0.00"), msg="worker")

    # ------------------------------------------------------------------
    # SE4 — payables / receivables restored (regression: reversal mirrors
    # must not leak into the obligation buckets)
    # ------------------------------------------------------------------

    def test_reverse_project_receivables_restored(self):
        """Before reversal the project held a 1000 receivable; after it is gone."""
        self.assert_receivables(self.project, AMOUNT, msg="project before")
        self._reversal()

        self.assert_receivables(self.project, Decimal("0.00"), msg="project after")

    def test_reverse_worker_payables_restored(self):
        """Before reversal the worker owed 1000; after it owes nothing."""
        self.assert_payables(self.worker, AMOUNT, msg="worker before")
        self._reversal()

        self.assert_payables(self.worker, Decimal("0.00"), msg="worker after")

    def test_reverse_project_payables_unchanged(self):
        self._reversal()

        self.assert_payables(self.project, Decimal("0.00"), msg="project")

    def test_reverse_worker_receivables_unchanged(self):
        self._reversal()

        self.assert_receivables(self.worker, Decimal("0.00"), msg="worker")

    # ------------------------------------------------------------------
    # Differential invariant — create + reverse leaves the world unchanged
    # ------------------------------------------------------------------

    def test_create_then_reverse_leaves_world_unchanged(self):
        """Balances, payables, receivables and ledger must all return to the
        pre-advance state after a full create + reverse cycle."""
        before = self.snapshot_state()

        op = make_worker_advance(self.project, self.worker, self.officer, AMOUNT)
        op.reverse(officer=self.officer)

        self.assert_state_unchanged(before, msg="create+reverse of worker advance")

    # ------------------------------------------------------------------
    # Reversal blocked by outstanding repayments
    # ------------------------------------------------------------------

    def test_reversal_blocked_when_repayment_exists(self):
        self.op.create_repayment_transaction(
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
