from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class ProjectFundingOperation(Operation):
    _issuance_transaction_type = TransactionType.PROJECT_FUNDING_ISSUANCE
    _payment_transaction_type = TransactionType.PROJECT_FUNDING_PAYMENT

    url_str = "project-funding"
    label = "Project Funding"
    _source_role = "url"
    _dest_role = "post"
    can_pay = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1

    class Meta:
        proxy = True
        verbose_name = "Project Funding"

    @property
    def payment_source_fund(self):
        return self.source.fund  # funder (person/shareholder)

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean_destination ensures this is a project

    @property
    def funder(self):
        return self.source

    @property
    def project(self):
        return self.destination

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

    def clean_source(self):
        if not self.source.person:
            raise ValidationError(
                "Project Funding source must be a Person entity."
            )

    def clean_destination(self):
        if not self.destination.project:
            raise ValidationError(
                "Project Funding destination must be a Project entity."
            )

    def clean(self):
        super().clean()
        # Shareholder check
        try:
            if self.source.person and self.destination.project:
                from apps.app_entity.models import StakeholderRole
                if not self.destination.stakeholders.filter(
                    target=self.source,
                    role=StakeholderRole.SHAREHOLDER,
                    active=True,
                ).exists():
                    raise ValidationError(
                        "The funding source must be a registered shareholder of the project."
                    )
        except ValidationError:
            raise
        except Exception:
            pass  # type errors handled by clean_source / clean_destination
        # Balance check (create only — amount is immutable so updates skip this)
        if self.pk:
            return
        try:
            fund = self.payment_source_fund
        except Exception:
            return
        if not fund.can_pay(self.amount):
            raise ValidationError(
                f"Insufficient funds: balance is {fund.balance}, "
                f"cannot fund {self.amount}."
            )
