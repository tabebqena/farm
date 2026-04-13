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
        return self.source.fund  # shareholder

    @property
    def payment_target_fund(self):
        return self.destination.fund  # project

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

