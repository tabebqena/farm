from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class BirthOperation(Operation):
    """
    Records a livestock birth event.

    A birth creates a new Animal/Batch in inventory with no cash flow —
    the system entity issues the asset value on behalf of the project.
    The invoice item's on-save handler creates the new Animal/Batch object
    (same as PURCHASE), distinguishing this from CAPITAL_GAIN which always
    links to an existing asset.
    """

    _issuance_transaction_type = TransactionType.BIRTH_ISSUANCE
    _payment_transaction_type = TransactionType.BIRTH_PAYMENT

    url_str = "birth"
    label = "Birth"
    _source_role = "system"
    _dest_role = "url"
    can_pay = False
    check_balance_on_payment = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1
    has_invoice = True
    creates_assets = True

    class Meta:
        proxy = True
        verbose_name = "Birth"

    @property
    def payment_source_fund(self):
        return self.source.fund  # system entity — exempt from balance validation

    @property
    def payment_target_fund(self):
        return self.destination.fund  # project receiving the newborn asset

    def clean_source(self):
        if not self.source.is_system:
            raise ValidationError("Birth source must be the System entity.")
