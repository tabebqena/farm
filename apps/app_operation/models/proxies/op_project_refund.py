from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class ProjectRefundOperation(Operation):
    _issuance_transaction_type = TransactionType.PROJECT_REFUND_ISSUANCE
    _payment_transaction_type = TransactionType.PROJECT_REFUND_PAYMENT

    url_str = "project-refunding"
    label = "Project Refund"
    _source_role = "post"
    _dest_role = "url"
    can_pay = False
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
        verbose_name = "Project Refund"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean_source ensures this is a project

    @property
    def payment_target_fund(self):
        return self.destination.fund  # funder (person/shareholder)

    @property
    def project(self):
        return self.source

    @property
    def funder(self):
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
        if not self.source.project:
            raise ValidationError("Project Refund source must be a Project entity.")

    def clean_destination(self):
        if not self.destination.person:
            raise ValidationError("Project Refund destination must be a Person entity.")

    def clean(self):
        super().clean()
        # Shareholder check
        try:
            if self.source.project and self.destination.person:
                from apps.app_entity.models import StakeholderRole
                if not self.source.stakeholders.filter(
                    target=self.destination,
                    role=StakeholderRole.SHAREHOLDER,
                    active=True,
                ).exists():
                    raise ValidationError(
                        "The refund destination must be a registered shareholder of the project."
                    )
        except ValidationError:
            raise
        except Exception:
            pass  # type errors handled by clean_source / clean_destination
        # Balance and investment-cap checks (new operations only; reversals bypass these)
        if self.pk or getattr(self, "reversal_of", None) is not None:
            return
        try:
            fund = self.payment_source_fund
        except Exception:
            return
        if not fund.can_pay(self.amount):
            raise ValidationError(
                f"Insufficient project funds: balance is {fund.balance}, "
                f"cannot refund {self.amount}."
            )
        # Refund must not exceed the net amount the shareholder has funded this project
        try:
            if self.source_id and self.destination_id and self.source.project and self.destination.person:
                from decimal import Decimal as D
                from django.db.models import Sum
                from apps.app_operation.models.operation_type import OperationType

                total_funded = (
                    Operation.objects.filter(
                        operation_type=OperationType.PROJECT_FUNDING,
                        source=self.destination,
                        destination=self.source,
                        reversal_of__isnull=True,
                        reversed_by__isnull=True,
                    ).aggregate(total=Sum("amount"))["total"]
                    or D("0.00")
                )
                total_refunded = (
                    Operation.objects.filter(
                        operation_type=OperationType.PROJECT_REFUND,
                        source=self.source,
                        destination=self.destination,
                        reversal_of__isnull=True,
                        reversed_by__isnull=True,
                    ).aggregate(total=Sum("amount"))["total"]
                    or D("0.00")
                )
                net_refundable = total_funded - total_refunded
                if self.amount > net_refundable:
                    raise ValidationError(
                        f"Refund amount {self.amount} exceeds the net amount funded "
                        f"({net_refundable}) by this shareholder."
                    )
        except ValidationError:
            raise
        except Exception:
            pass
