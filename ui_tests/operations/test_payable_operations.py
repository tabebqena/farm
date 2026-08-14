"""UI clause tests for the payable / repayable generic-form operations.

Covers op_8 Loan (issuance + repayment) and op_11 Worker Advance (one-shot
advance + repayment) from their specs under docs/specs/operations/. Each test
opens a real browser, performs setup, executes exactly one spec clause, and
asserts the visible response.
"""
from decimal import Decimal

from django.db.models import Q

from ui_tests.base import UiTestCase, make_person, make_worker, inject_person_fund


class PayableOpClauseMixin:
    """Shared clause tests for a payable/repayable operation.

    Concrete classes inherit from it plus ``UiTestCase``. Configure:
      op_type, primary_name, secondary_factory, fund_primary.
    """

    op_type = None
    primary_name = "Payable Entity"
    secondary_factory = None
    fund_primary = None
    fund_secondary = None
    disburse_before_repay = False

    def _primary(self):
        return make_person(self.primary_name)

    def _secondary(self):
        return self.secondary_factory() if self.secondary_factory else None

    def _extra_setup(self, primary, secondary):
        pass

    def _latest_op(self, entity):
        from apps.app_operation.models import Operation

        return (
            Operation.objects.filter(Q(source=entity) | Q(destination=entity))
            .latest("created_at")
        )

    def _make_created(self, amount=Decimal("300.00")):
        primary = self._primary()
        secondary = self._secondary()
        self._extra_setup(primary, secondary)
        if self.fund_primary:
            inject_person_fund(self.world, primary, self.fund_primary, self.officer)
        if self.fund_secondary and secondary is not None:
            inject_person_fund(self.world, secondary, self.fund_secondary, self.officer)
        self.login_as_officer()
        self.create_one_shot(self.op_type, primary, amount, secondary=secondary)
        return primary, self._latest_op(primary)

    def test_sc_create_success(self):
        """SC effect: the create flow records the operation and shows the total."""
        primary, op = self._make_created()
        self.assert_flash_contains("recorded successfully")
        self.assert_visible_text("300.00")

    def test_repay(self):
        """A7 repay: a repayment is recorded and the detail shows the recovery.

        Loans must be disbursed first (A6) — repayable_amount is capped by the
        settled/disbursed amount (spec SC6).
        """
        primary, op = self._make_created()
        if self.disburse_before_repay:
            self.record_payment(op, Decimal("300.00"))
        self.record_repayment(op, Decimal("100.00"))
        self.assert_flash_contains("Repayment")
        self.assert_visible_text("100.00")

    def test_vr5_reason_required(self):
        """VR5: reversing with an empty reason shows the error and stays put."""
        primary, op = self._make_created()
        self.goto("operation_reverse_view", op.pk)
        self.disable_html5_validation()
        self.click_submit()
        self.assert_flash_contains("A reason for reversal is required.")
        self.assertTrue(
            "reverse" in self.driver.current_url,
            f"expected to stay on the reverse form, got {self.driver.current_url}",
        )


class LoanUiTests(PayableOpClauseMixin, UiTestCase):
    """op_8 Loan: person creditor (url) -> person debtor (post picker), repayable.

    Per spec SC6 a loan is only repayable after disbursement, and the debtor pays
    the repayment from their fund, so both are funded.
    """
    op_type = "loan"
    primary_name = "Loan Creditor"
    fund_primary = Decimal("1000.00")
    fund_secondary = Decimal("500.00")
    disburse_before_repay = True
    secondary_factory = staticmethod(lambda: make_person("Loan Debtor"))


class WorkerAdvanceUiTests(PayableOpClauseMixin, UiTestCase):
    """op_11 Worker Advance: project (url) -> worker (post picker), one-shot + repay.

    self.project (created + funded in setUp) is the source; a worker linked to it
    is picked as the destination.
    """
    op_type = "worker-advance"
    primary_name = "Advance Project"

    def _primary(self):
        return self.project

    def _secondary(self):
        return make_worker(self.project, "Advance Worker")
