from typing import List

from django.core.exceptions import ValidationError

from apps.app_transaction.transaction_type import TransactionType

from apps.app_operation.models.operation import Operation


class LoanOperation(Operation):
    _issuance_transaction_type = TransactionType.LOAN_ISSUANCE
    _payment_transaction_type = TransactionType.LOAN_PAYMENT
    _repayment_transaction_type = TransactionType.LOAN_REPAYMENT

    url_str = "loan"
    label = "Debt Issuance"
    _source_role = "url"
    _dest_role = "post"
    can_pay = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = False
    has_repayment = True
    repayment_label = "Loan Recovery"
    max_payment_transaction_count = -1

    class Meta:
        proxy = True
        verbose_name = "Loan"

    @property
    def payment_source_fund(self):
        return self.source.fund  # creditor disburses

    @property
    def payment_target_fund(self):
        return self.destination.fund  # debtor receives

    @property
    def creditor(self):
        return self.source

    @property
    def debtor(self):
        return self.destination

    @property
    def _reversable_transaction_types(self) -> List[TransactionType]:
        # Loans must have repayments manually cleared before reversal is allowed.
        return [TransactionType.LOAN_ISSUANCE, TransactionType.LOAN_PAYMENT]

    @property
    def _implicit_reversable_transaction_types(self) -> List[TransactionType]:
        # Only the issuance is implicitly reversed; payments must be cleared manually.
        return [TransactionType.LOAN_ISSUANCE]


class WorkerAdvanceOperation(Operation):
    _issuance_transaction_type = TransactionType.WORKER_ADVANCE_ISSUANCE
    _payment_transaction_type = TransactionType.WORKER_ADVANCE_PAYMENT
    _repayment_transaction_type = TransactionType.WORKER_ADVANCE_REPAYMENT

    url_str = "worker-advance"
    label = "Worker Advance Issuance"
    _source_role = "url"
    _dest_role = "post"
    can_pay = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = True
    repayment_label = "Advance Repayment"
    max_payment_transaction_count = 1

    class Meta:
        proxy = True
        verbose_name = "Worker Advance"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean_source ensures this is a project (advances)

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean_destination ensures this is an active worker

    def clean_source(self):
        if not self.source.project:
            raise ValidationError("Worker advance source should be a project.")

    def clean_destination(self):
        if not self.destination.person:
            raise ValidationError("Worker Advance destination must be a person entity.")
        from apps.app_entity.models import Stakeholder

        if not Stakeholder.objects.filter(
            parent=self.source, target=self.destination, active=True
        ).exists():
            raise ValidationError(
                "Worker Advance destination must be an active worker in the selected project."
            )
