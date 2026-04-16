from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class CapitalLossOperation(Operation):
    _issuance_transaction_type = TransactionType.CAPITAL_LOSS_ISSUANCE
    _payment_transaction_type = TransactionType.CAPITAL_LOSS_PAYMENT

    url_str = "capital-loss"
    label = "Capital Loss Issuance"
    _source_role = "url"
    _dest_role = "system"
    can_pay = False
    # No balance check: capital loss is an accounting write-down entry, not a real cash
    # outflow. The system entity sits on the destination side; the source entity is
    # recording a loss, not transferring spendable funds.
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
        verbose_name = "Capital Loss"

    @property
    def payment_source_fund(self):
        return self.source.fund  # entity absorbing the loss

    @property
    def payment_target_fund(self):
        return (
            self.destination.fund
        )  # clean_destination ensures this is the system entity

    def clean_destination(self):
        if not self.destination.is_system:
            raise ValidationError("Capital Loss destination must be the System entity.")
