from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


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

    @classmethod
    def get_related_entities(cls, url_entity, config):
        from apps.app_entity.models import Stakeholder, StakeholderRole
        relationships = (
            Stakeholder.objects.filter(
                parent=url_entity, role=StakeholderRole.WORKER, active=True
            )
            .select_related("target")
            .all()
        )
        return [s.target for s in relationships]

    def clean_destination(self):
        if not self.destination.person:
            raise ValidationError("Worker Advance destination must be a person entity.")
        from apps.app_entity.models import Stakeholder, StakeholderRole

        if not Stakeholder.objects.filter(
            parent=self.source, target=self.destination, role=StakeholderRole.WORKER, active=True
        ).exists():
            raise ValidationError(
                "Worker Advance destination must be an active worker in the selected project."
            )

    def clean(self):
        super().clean()
        if self.source_id and hasattr(self.source, "fund"):
            fund = self.source.fund
            if self.amount and fund.balance < self.amount:
                raise ValidationError(
                    f"Insufficient funds: project fund balance ({fund.balance}) "
                    f"is less than the advance amount ({self.amount})."
                )

    def _requires_transaction_reversal(self, all_txs) -> bool:
        if super()._requires_transaction_reversal(all_txs):
            return True
        repayments = all_txs.filter(
            type=TransactionType.WORKER_ADVANCE_REPAYMENT,
            reversal_of__isnull=True,
            reversed_by__isnull=True,
        )
        return repayments.exists()
