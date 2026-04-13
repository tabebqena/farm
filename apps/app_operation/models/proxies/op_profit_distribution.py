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
        return self.source.fund  # clean_source ensures this is a project

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean_destination ensures this is a shareholder

    @property
    def project(self):
        return self.source

    @property
    def shareholder(self):
        return self.destination

    def clean_source(self):
        if not self.source.project:
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

