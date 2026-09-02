"""Worker-advance operation proxy.

:class:`WorkerAdvanceOperation` records an advance given to a worker and tracks
the outstanding balance through repayments against the worker's wages.
"""

from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import (
    LinkedRePaymentTransactionMixin,
    OneShotTransactionMixin,
    Operation,
)
from apps.app_transaction.transaction_type import TransactionType


class WorkerAdvanceOperation(
    OneShotTransactionMixin, LinkedRePaymentTransactionMixin, Operation
):
    """Concrete operation proxy for a worker advance.

    Records an advance given to a worker and tracks the outstanding balance
    through repayments made against the worker's wages.
    """

    _issuance_transaction_type = TransactionType.WORKER_ADVANCE_ISSUANCE
    _payment_transaction_type = TransactionType.WORKER_ADVANCE_PAYMENT
    _repayment_transaction_type = TransactionType.WORKER_ADVANCE_REPAYMENT
    is_repayable = True

    url_str = "worker-advance"
    label = "Worker Advance Issuance"
    _source_role = "url"
    _dest_role = "post"
    # One-shot issuance + payment at creation, plus repayments (non-default).
    has_repayment = True
    repayment_label = "Advance Repayment"

    class Meta:
        proxy = True
        verbose_name = "Worker Advance"

    @property
    def payment_source_fund(self):
        return self.source  # clean_source ensures this is a project (advances)

    @property
    def payment_target_fund(self):
        return self.destination  # clean_destination ensures this is an active worker

    def clean_source(self):
        if not self.source.is_project:
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
        if not self.destination.is_person:
            raise ValidationError("Worker Advance destination must be a person entity.")
        from apps.app_entity.models import Stakeholder, StakeholderRole

        if not Stakeholder.objects.filter(
            parent=self.source,
            target=self.destination,
            role=StakeholderRole.WORKER,
            active=True,
        ).exists():
            raise ValidationError(
                "Worker Advance destination must be an active worker in the selected project."
            )

    def clean(self):
        super().clean()
        if self.source_id:
            # Route through can_pay so the virtual (system/world) exemption and the
            # active-entity rule stay centralized on the Entity model.
            if self.amount and not self.source.can_pay(self.amount):
                raise ValidationError(
                    f"Insufficient funds: project fund balance ({self.source.balance}) "
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
