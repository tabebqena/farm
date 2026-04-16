from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class LossCoverageOperation(Operation):
    _issuance_transaction_type = TransactionType.LOSS_COVERAGE_ISSUANCE
    _payment_transaction_type = TransactionType.LOSS_COVERAGE_PAYMENT

    url_str = "loss-coverage"
    label = "Loss Coverage"
    _source_role = "url"
    _dest_role = "post"
    can_pay = False
    # Balance check required: the shareholder fund is the real payer. For this one-shot
    # operation the check runs at creation time and fails the whole op if insufficient.
    check_balance_on_payment = True
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1

    class Meta:
        proxy = True
        verbose_name = "Loss Coverage"

    @property
    def payment_source_fund(self):
        return self.source  # shareholder

    @property
    def payment_target_fund(self):
        return self.destination  # project

    @classmethod
    def get_related_entities(cls, url_entity, config):
        from apps.app_entity.models import Entity, StakeholderRole

        return (
            Entity.objects.filter(
                project__isnull=False,
                stakeholders__target=url_entity,
                stakeholders__active=True,
                stakeholders__role=StakeholderRole.SHAREHOLDER,
            )
            .distinct()
            .all()
        )

    @property
    def shareholder(self):
        return self.source

    @property
    def project(self):
        return self.destination

    def clean(self):
        if self.plan_id is None:
            raise ValidationError("Loss Coverage requires a Distribution Plan.")
        plan = self.plan
        if not plan.is_loss:
            raise ValidationError(
                "The linked Distribution Plan has no loss to cover "
                f"(amount={plan.amount})."
            )
        if self.amount is not None:
            remaining = plan.remaining_coverable
            # Exclude the current operation's own amount when editing
            if self.pk:
                from apps.app_operation.models.operation import Operation
                from apps.app_operation.models.operation_type import OperationType

                own = Operation.objects.filter(
                    pk=self.pk,
                    operation_type=OperationType.LOSS_COVERAGE,
                    reversal_of__isnull=True,
                    reversed_by__isnull=True,
                ).values_list("amount", flat=True).first() or Decimal("0.00")
                remaining += own
            if self.amount > remaining:
                raise ValidationError(
                    f"Amount {self.amount} exceeds remaining coverable loss "
                    f"{remaining} for this plan."
                )
        return super().clean()
