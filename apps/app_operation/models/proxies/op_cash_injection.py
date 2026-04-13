from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class CashInjectionOperation(Operation):
    _issuance_transaction_type = TransactionType.CASH_INJECTION_ISSUANCE
    _payment_transaction_type = TransactionType.CASH_INJECTION_PAYMENT

    url_str = "cash-injection"
    label = "Cash Injection"
    _source_role = "world"
    _dest_role = "url"
    can_pay = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1
    theme_color = "success"
    theme_icon = "bi-box-arrow-in-down"

    class Meta:
        proxy = True
        verbose_name = "Cash Injection"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean_source ensures this is the world entity

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean_destination ensures this is a person

    def clean_source(self):
        if not self.source.is_world:
            raise ValidationError("Cash Injection source must be the World entity.")

    def clean_destination(self):
        if not self.destination.person:
            raise ValidationError("Cash Injection must target a Person entity.")
