from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class ProfitDistributionOperation(Operation):
    _issuance_transaction_type = TransactionType.PROFIT_DISTRIBUTION_ISSUANCE
    _payment_transaction_type = TransactionType.PROFIT_DISTRIBUTION_PAYMENT

    url_str = "profit-distribution"
    label = "Profit Distribution"
    _source_role = "url"
    _dest_role = "post"
    can_pay = False
    # Balance check required: the project fund is the real payer. For this one-shot
    # operation the check runs at creation time and fails the whole op if insufficient.
    check_balance_on_payment = True
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1
    theme_color = "success"
    theme_icon = "bi-box-arrow-in-down"

    class Meta:
        proxy = True
        verbose_name = "Profit Distribution"

    @property
    def payment_source_fund(self):
        return self.source  # clean_source ensures this is a project

    @property
    def payment_target_fund(self):
        return self.destination  # clean_destination ensures this is a shareholder

    @property
    def project(self):
        return self.source

    @property
    def shareholder(self):
        return self.destination

    def clean_source(self):
        if not self.source.is_project:
            raise ValidationError(
                "Profit Distribution source must be a Project entity."
            )

    @classmethod
    def get_related_entities(cls, url_entity, config):
        from apps.app_entity.models import Stakeholder, StakeholderRole

        shareholder_relationships = (
            Stakeholder.objects.filter(
                parent=url_entity, role=StakeholderRole.SHAREHOLDER, active=True
            )
            .select_related("target")
            .all()
        )
        return [s.target for s in shareholder_relationships]

    def clean_destination(self):
        if not self.destination.is_shareholder:
            raise ValidationError(
                "Profit Distribution destination must be a Shareholder."
            )

    def clean(self):
        if self.plan_id is None:
            raise ValidationError("Profit Distribution requires a Distribution Plan.")
        plan = self.plan
        if not plan.is_profit:
            raise ValidationError(
                "The linked Distribution Plan has no profit to distribute "
                f"(amount={plan.amount})."
            )
        if self.amount is not None:
            remaining = plan.remaining_distributable
            # Exclude the current operation's own amount when editing
            if self.pk:
                from apps.app_operation.models.operation import Operation
                from apps.app_operation.models.operation_type import OperationType

                own = Operation.objects.filter(
                    pk=self.pk,
                    operation_type=OperationType.PROFIT_DISTRIBUTION,
                    reversal_of__isnull=True,
                    reversed_by__isnull=True,
                ).values_list("amount", flat=True).first() or Decimal("0.00")
                remaining += own
            if self.amount > remaining:
                raise ValidationError(
                    f"Amount {self.amount} exceeds remaining distributable profit "
                    f"{remaining} for this plan."
                )
        return super().clean()
