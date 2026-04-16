from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class CapitalGainOperation(Operation):
    _issuance_transaction_type = TransactionType.CAPITAL_GAIN_ISSUANCE
    _payment_transaction_type = TransactionType.CAPITAL_GAIN_PAYMENT

    url_str = "capital-gain"
    label = "Capital Gain Issuance"
    _source_role = "system"
    _dest_role = "url"
    can_pay = False
    # No balance check: the system entity is always the payer here.
    # System entities are exempt from balance validation by design — they represent
    # the accounting system itself, not a real-money holder.
    check_balance_on_payment = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1
    has_invoice = True

    class Meta:
        proxy = True
        verbose_name = "Capital Gain"

    @property
    def payment_source_fund(self):
        # No balance check: the system entity is always the payer here.
        # System entities are exempt from fund balance validation by design.
        return self.source  # clean_source ensures this is the system entity

    @property
    def payment_target_fund(self):
        return self.destination  # entity receiving the gain

    def clean_source(self):
        if not self.source.is_system:
            raise ValidationError("Capital Gain source must be the System entity.")
