from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class ConsumptionOperation(Operation):
    """
    Records internal consumption of a product we own.

    Consumption removes an existing inventory asset from the project with no
    cash flow — the project's asset value is written off to the system entity.
    The invoice item links to the existing product/asset being consumed.
    """

    _issuance_transaction_type = TransactionType.CONSUMPTION_ISSUANCE
    _payment_transaction_type = TransactionType.CONSUMPTION_PAYMENT

    url_str = "consumption"
    label = "Consumption"
    _source_role = "url"
    _dest_role = "system"
    can_pay = False
    check_balance_on_payment = False
    is_partially_payable = False
    has_category = False
    category_required = False
    has_invoice = True
    creates_assets = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1

    class Meta:
        proxy = True
        verbose_name = "Consumption"

    @property
    def payment_source_fund(self):
        return self.source.fund  # project absorbing the write-off

    @property
    def payment_target_fund(self):
        return self.destination.fund  # system entity — exempt from balance validation

    @property
    def project(self):
        return self.source

    def clean_source(self):
        if not self.source.is_project:
            raise ValidationError("Consumption source must be a Project entity.")

    def clean_destination(self):
        if not self.destination.is_system:
            raise ValidationError("Consumption destination must be the System entity.")
