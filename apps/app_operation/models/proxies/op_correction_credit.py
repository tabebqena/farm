from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class CorrectionCreditOperation(Operation):
    _issuance_transaction_type = TransactionType.CORRECTION_CREDIT_ISSUANCE
    _payment_transaction_type = TransactionType.CORRECTION_CREDIT_PAYMENT

    url_str = "correction-credit"
    label = "Correction Credit"
    _source_role = "system"
    _dest_role = "url"
    can_pay = False
    # No balance check: the system entity is always the payer here. Corrections are an
    # admin-only tool to fix wrong calculations; they must be unrestricted by balance
    # so that errors in the ledger can always be corrected.
    check_balance_on_payment = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1
    theme_color = "success"
    theme_icon = "bi-patch-plus"

    class Meta:
        proxy = True
        verbose_name = "Correction Credit"

    @property
    def payment_source_fund(self):
        return self.source.fund  # system entity

    @property
    def payment_target_fund(self):
        return self.destination.fund  # project entity

    def clean_source(self):
        if not self.source.is_system:
            raise ValidationError("Correction Credit source must be the System entity.")

    def clean_destination(self):
        if not self.destination.project:
            raise ValidationError("Correction Credit destination must be a Project entity.")
