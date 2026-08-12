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


class WorkerAdvanceRepaymentTest(BaseOperationTestCase):
    """
    Tests for WORKER_ADVANCE_REPAYMENT transactions — worker returning the
    advance to the project fund.

    The worker's fund is already seeded by the advance (WORKER_ADVANCE_PAYMENT),
    so no additional injection is needed before repayments.
    """

    def setUp(self):
        super().setUp()
        self.worker = make_worker(self.project, "Ali Worker")
        self.op = make_worker_advance(
            self.project, self.worker, self.officer, AMOUNT
        )

    def _repay(self, amount):
        self.op.create_repayment_transaction(
            amount=amount,
            officer=self.officer,
            date=date.today(),
        )

    def _repayment(self, amount=None):
        qs = self.op.get_all_transactions().filter(
            type=TransactionType.WORKER_ADVANCE_REPAYMENT,
            reversal_of__isnull=True,
        )
        if amount is not None:
            qs = qs.filter(amount=amount)
        return qs.get()

    # ------------------------------------------------------------------
    # SE2 — repayment transaction
    # ------------------------------------------------------------------

    def test_repayment_creates_repayment_tx_exact(self):
        self._repay(Decimal("400.00"))

        self.assert_tx(
            self.op,
            TransactionType.WORKER_ADVANCE_REPAYMENT,
            self.worker,
            self.project,
            Decimal("400.00"),
        )

    def test_repayment_creates_exactly_one_repayment(self):
        self._repay(Decimal("400.00"))

        self.assert_tx_types(
            self.op,
            {
                TransactionType.WORKER_ADVANCE_ISSUANCE: 1,
                TransactionType.WORKER_ADVANCE_PAYMENT: 1,
                TransactionType.WORKER_ADVANCE_REPAYMENT: 1,
            },
        )

    # ------------------------------------------------------------------
    # SE3 — fund balances
    # ------------------------------------------------------------------

    def test_worker_fund_decreases_after_repayment(self):
        self._repay(Decimal("400.00"))

        self.assert_balance(self.worker, Decimal("600.00"), msg="worker")

    def test_project_fund_increases_after_repayment(self):
        self._repay(Decimal("400.00"))

        self.assert_balance(
            self.project,
            self.project_funding - AMOUNT + Decimal("400.00"),
            msg="project",
        )

    # ------------------------------------------------------------------
    # SE4 — payables / receivables
    # ------------------------------------------------------------------

    def test_repayment_decreases_project_receivables(self):
        """Before: project is owed the full advance; after a 400 repayment it is
        owed 600."""
        self.assert_receivables(self.project, AMOUNT, msg="project before")
        self._repay(Decimal("400.00"))

        self.assert_receivables(self.project, Decimal("600.00"), msg="project after")

    def test_repayment_decreases_worker_payables(self):
        self.assert_payables(self.worker, AMOUNT, msg="worker before")
        self._repay(Decimal("400.00"))

        self.assert_payables(self.worker, Decimal("600.00"), msg="worker after")

    def test_full_repayment_zeroes_project_receivables(self):
        self._repay(AMOUNT)

        self.assert_receivables(self.project, Decimal("0.00"), msg="project")

    def test_full_repayment_zeroes_worker_payables(self):
        self._repay(AMOUNT)

        self.assert_payables(self.worker, Decimal("0.00"), msg="worker")

    # ------------------------------------------------------------------
    # SE8 — derived repayment amount
    # ------------------------------------------------------------------

    def test_amount_remaining_to_repay_decreases_after_repayment(self):
        self._repay(Decimal("400.00"))

        self.assertEqual(self.op.amount_remaining_to_repay, Decimal("600.00"))

    def test_multiple_partial_repayments_accumulate(self):
        self._repay(Decimal("300.00"))
        self._repay(Decimal("300.00"))

        self.assertEqual(self.op.amount_remaining_to_repay, Decimal("400.00"))

    def test_full_repayment_marks_as_fully_repayed(self):
        self._repay(AMOUNT)

        self.assertTrue(self.op.is_fully_repayed)
        self.assertEqual(self.op.amount_remaining_to_repay, Decimal("0.00"))

    # ------------------------------------------------------------------
    # Over-repayment blocked
    # ------------------------------------------------------------------

    def test_repayment_exceeding_advance_amount_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._repay(Decimal("1500.00"))

    def test_partial_repayment_then_over_repayment_raises_validation_error(self):
        self._repay(Decimal("800.00"))

        with self.assertRaises(ValidationError):
            self._repay(Decimal("300.00"))  # only 200 remaining

    def test_zero_repayment_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self._repay(Decimal("0.00"))

    # ------------------------------------------------------------------
    # Reversal of repayment — derived amounts
    # ------------------------------------------------------------------

    def test_full_repayment_reversed_restores_remaining_balance(self):
        """Reversing the only (full) repayment must un-mark the operation as repaid."""
        self._repay(AMOUNT)
        self.assertTrue(self.op.is_fully_repayed)

        self._repayment().reverse(officer=self.officer)

        self.op.refresh_from_db()
        self.assertEqual(self.op.amount_repayed, Decimal("0.00"))
        self.assertFalse(self.op.is_fully_repayed)
        self.assertEqual(self.op.amount_remaining_to_repay, AMOUNT)

    def test_partial_repayment_reversed_restores_remaining_balance(self):
        """Reversing a partial repayment increases the remaining balance again."""
        self._repay(Decimal("400.00"))
        self.assertEqual(self.op.amount_remaining_to_repay, Decimal("600.00"))

        self._repayment().reverse(officer=self.officer)

        self.op.refresh_from_db()
        self.assertEqual(self.op.amount_repayed, Decimal("0.00"))
        self.assertFalse(self.op.is_fully_repayed)
        self.assertEqual(self.op.amount_remaining_to_repay, AMOUNT)

    def test_only_reversed_repayment_is_net_out(self):
        """Reversing one of several repayments nets out only that amount."""
        self._repay(Decimal("600.00"))
        self._repay(Decimal("400.00"))
        self.assertTrue(self.op.is_fully_repayed)

        self._repayment(amount=Decimal("400.00")).reverse(officer=self.officer)

        self.op.refresh_from_db()
        self.assertEqual(self.op.amount_repayed, Decimal("600.00"))
        self.assertFalse(self.op.is_fully_repayed)
        self.assertEqual(self.op.amount_remaining_to_repay, Decimal("400.00"))

    # ------------------------------------------------------------------
    # Reversal of repayment — SE4 payables / receivables (regression: the
    # reversal mirror must not leak into the obligation buckets)
    # ------------------------------------------------------------------

    def test_reversed_repayment_restores_project_receivables(self):
        """After reversing a full repayment the project is owed the advance again."""
        self._repay(AMOUNT)
        self.assert_receivables(self.project, Decimal("0.00"), msg="project before")

        self._repayment().reverse(officer=self.officer)

        self.assert_receivables(self.project, AMOUNT, msg="project after")

    def test_reversed_repayment_restores_worker_payables(self):
        self._repay(AMOUNT)
        self.assert_payables(self.worker, Decimal("0.00"), msg="worker before")

        self._repayment().reverse(officer=self.officer)

        self.assert_payables(self.worker, AMOUNT, msg="worker after")

    def test_reversed_repayment_keeps_project_payables_zero(self):
        """The reversal mirror must not leak onto the project's payables as a
        negative 'Settle' row (regression)."""
        self._repay(AMOUNT)
        self.assert_payables(self.project, Decimal("0.00"), msg="project before")

        self._repayment().reverse(officer=self.officer)

        self.assert_payables(self.project, Decimal("0.00"), msg="project after")

    # ------------------------------------------------------------------
    # Differential invariant — repay + reverse repayment returns to advance state
    # ------------------------------------------------------------------

    def test_repay_then_reverse_repayment_returns_to_advance_state(self):
        """The world after (advance + full repay + reverse repayment) must equal
        the world after just the advance."""
        before = self.snapshot_state()  # advance-only state

        self._repay(AMOUNT)
        self._repayment().reverse(officer=self.officer)

        self.assert_state_unchanged(before, msg="repay + reverse repayment")
