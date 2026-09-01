"""UI happy-path tests for op_12 Expense (docs/specs/operations/op_12_expense.md).

Happy path per repo guidance: create -> pay -> reverse. Per spec §5.2 (VR3) an
expense with an active payment cannot be reversed until that payment transaction
is reversed first, so the full happy path also undoes the payment before the
operation-level reversal.
"""
from decimal import Decimal

from django.db.models import Q

from apps.app_operation.models.operation_type import OperationType
from apps.app_transaction.transaction_type import TransactionType

from ui_tests.base import UiTestCase
from ui_tests.operations.helpers import make_category


class ExpenseUiTests(UiTestCase):
    """op_12 Expense: project -> world, category required, partially payable."""

    def _latest_expense(self):
        from apps.app_operation.models import Operation

        return (
            Operation.objects.filter(
                Q(source=self.project) | Q(destination=self.project),
                operation_type=OperationType.EXPENSE,
            ).latest("created_at")
        )

    def _create_expense(self, amount=Decimal("200.00")):
        cat = make_category(self.project, name="Salaries")
        self.login_as_officer()
        self.goto("operation_create_view", self.project.pk, "expense")
        self.select("category", cat.pk)
        self.fill_amount(f"{amount:.2f}")
        self.fill("description", "UI expense")
        self.click_submit()
        self.wait_for_url_contains("detail")
        return self._latest_expense()

    def test_happy_path_create_pay_reverse(self):
        """Create -> pay (partial) -> reverse payment -> reverse; each step leaves
        a visible trace."""
        op = self._create_expense()
        self.assert_flash_contains("recorded successfully")
        self.assert_visible_text("Expense")
        self.assert_visible_text("200.00")

        # A6 pay
        self.record_payment(op, Decimal("100.00"))
        self.assert_flash_contains("Payment")
        self.assert_visible_text("100.00")

        # VR3: an expense with an active payment is blocked from operation-level
        # reversal — undo the payment transaction first.
        payment_tx = (
            op.get_all_transactions().filter(type=TransactionType.EXPENSE_PAYMENT)
            .latest("created_at")
        )
        self.reverse_transaction(payment_tx, reason="UI payment data entry error")
        self.assert_flash_contains("reversed successfully")

        # reverse the operation
        self.reverse_operation(op, reason="UI test data entry error")
        self.assert_visible_text("Operation Voided (Reversed)")
