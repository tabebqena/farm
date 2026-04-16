from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class ExpenseOperation(Operation):
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
    category_required = True
    has_invoice = False
    _is_one_shot_operation = False
    has_repayment = False
    max_payment_transaction_count = -1

    category_type = "EXPENSE"

    class Meta:
        proxy = True
        verbose_name = "Expense"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean_source ensures this is a project (pays)

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean_destination ensures this is world

    @property
    def project(self):
        return self.source

    def clean_source(self):
        if not self.source.is_project:
            raise ValidationError("Expense source must be a Project entity.")

    def clean_destination(self):
        if not self.destination.is_world:
            raise ValidationError("Expense destination must be the World entity.")
