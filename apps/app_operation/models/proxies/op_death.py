from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class DeathOperation(Operation):
    """
    Records a livestock death event.

    A death removes an existing Animal/Batch from active inventory with no cash
    flow — the project's asset value is written off to the system entity.
    The invoice item links to the existing Animal/Batch (same as CAPITAL_LOSS),
    but signals to the save handler that the asset should be marked as deceased
    rather than merely devalued.
    """

    _issuance_transaction_type = TransactionType.DEATH_ISSUANCE
    _payment_transaction_type = TransactionType.DEATH_PAYMENT

    url_str = "death"
    label = "Death"
    _source_role = "url"
    _dest_role = "system"
    can_pay = False
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
        verbose_name = "Death"

    @property
    def payment_source_fund(self):
        return self.source  # project absorbing the write-off

    @property
    def payment_target_fund(self):
        return self.destination  # system entity — exempt from balance validation

    def clean_destination(self):
        if not self.destination.is_system:
            raise ValidationError("Death destination must be the System entity.")
