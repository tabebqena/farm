"""Expense-operation proxy.

:class:`ExpenseOperation` records an expense against a project / vendor; the
amount is adjustable and a linked payment transaction is created.
"""

from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import AdjustableTransactionMixin, Operation
from apps.app_transaction.transaction_type import TransactionType


class ExpenseOperation(AdjustableTransactionMixin, Operation):
    """Concrete operation proxy for an expense.

    Records an adjustable expense charged by a project / vendor; the project fund
    is the payer, so it is partially payable and each payment is balance-checked.
    """

    _issuance_transaction_type = TransactionType.EXPENSE_ISSUANCE
    _payment_transaction_type = TransactionType.EXPENSE_PAYMENT

    url_str = "expense"
    label = "Expense Issuance"
    _source_role = "url"
    _dest_role = "world"
    can_pay = True
    # Balance check required: the project fund is the real payer. Issuance can succeed
    # with insufficient balance; each individual payment is guarded at settlement time.
    check_balance_on_payment = True
    is_partially_payable = True
    has_category = True
    has_invoice = False
    _is_one_shot_operation = False
    has_repayment = False
    max_payment_transaction_count = -1

    is_adjustable = True

    class Meta:
        proxy = True
        verbose_name = "Expense"

    @property
    def payment_source_fund(self):
        """The project fund paying the expense."""
        return self.source  # clean_source ensures this is a project (pays)

    @property
    def payment_target_fund(self):
        """The destination fund receiving the expense payment."""
        return self.destination  # clean_destination ensures this is world

    @property
    def project(self):
        """The project incurring the expense (the source entity)."""
        return self.source

    def clean_source(self):
        """Require the expense source to be a Project entity."""
        if not self.source.is_project:
            raise ValidationError("Expense source must be a Project entity.")

    def clean_destination(self):
        """Require the expense destination to be the World entity."""
        if not self.destination.is_world:
            raise ValidationError("Expense destination must be the World entity.")
