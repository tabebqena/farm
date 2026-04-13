from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class CashWithdrawalOperation(Operation):
    _issuance_transaction_type = TransactionType.CAPITAL_WITHDRAWAL_ISSUANCE
    _payment_transaction_type = TransactionType.CAPITAL_WITHDRAWAL_PAYMENT

    url_str = "cash-withdrawal"
    label = "Cash Withdrawal"
    _source_role = "url"
    _dest_role = "world"
    can_pay = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1
    check_balance_on_payment = True

    class Meta:
        proxy = True
        verbose_name = "Cash Withdrawal"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean_source ensures this is a person

    @property
    def payment_target_fund(self):
        return (
            self.destination.fund
        )  # clean_destination ensures this is the world entity

    def clean_source(self):
        if not self.source.person:
            raise ValidationError("Cash Withdrawal source must be a Person entity.")

    def clean_destination(self):
        if not self.destination.is_world:
            raise ValidationError(
                "Cash Withdrawal destination must be the World entity."
            )
