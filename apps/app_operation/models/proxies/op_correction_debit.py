from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class CorrectionDebitOperation(Operation):
    _issuance_transaction_type = TransactionType.CORRECTION_DEBIT_ISSUANCE
    _payment_transaction_type = TransactionType.CORRECTION_DEBIT_PAYMENT

    url_str = "correction-debit"
    label = "Correction Debit"
    _source_role = "url"
    _dest_role = "system"
    can_pay = False
    # No balance check: corrections are an admin-only tool to fix wrong calculations.
    # The destination is always the system entity; restricting corrections by fund
    # balance would prevent admins from fixing ledger errors.
    check_balance_on_payment = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1
    theme_color = "danger"
    theme_icon = "bi-patch-minus"

    class Meta:
        proxy = True
        verbose_name = "Correction Debit"

    @property
    def payment_source_fund(self):
        return self.source.fund  # project entity

    @property
    def payment_target_fund(self):
        return self.destination.fund  # system entity

    def clean_source(self):
        if not self.source.is_project:
            raise ValidationError("Correction Debit source must be a Project entity.")

    def clean_destination(self):
        if not self.destination.is_system:
            raise ValidationError(
                "Correction Debit destination must be the System entity."
            )
