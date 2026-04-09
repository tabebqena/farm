from django.core.exceptions import ValidationError

from apps.app_transaction.transaction_type import TransactionType

from apps.app_operation.models.operation import Operation


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


class ProfitDistributionOperation(Operation):
    _issuance_transaction_type = TransactionType.PROFIT_DISTRIBUTION_ISSUANCE
    _payment_transaction_type = TransactionType.PROFIT_DISTRIBUTION_PAYMENT

    url_str = "profit-distribution"
    label = "Profit Distribution"
    _source_role = "url"
    _dest_role = "post"
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


class LossCoverageOperation(Operation):
    _issuance_transaction_type = TransactionType.LOSS_COVERAGE_ISSUANCE
    _payment_transaction_type = TransactionType.LOSS_COVERAGE_PAYMENT

    url_str = "loss-coverage"
    label = "Loss Coverage"
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


class InternalTransferOperation(Operation):
    _issuance_transaction_type = TransactionType.INTERNAL_TRANSFER_ISSUANCE
    _payment_transaction_type = TransactionType.INTERNAL_TRANSFER_PAYMENT

    url_str = "internal-transfer"
    label = "Internal Transfer"
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
        verbose_name = "Internal Transfer"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean ensures this is an internal entity

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean ensures this is an internal entity

    @classmethod
    def get_related_entities(cls, url_entity, config):
        from apps.app_entity.models import Entity
        return Entity.objects.filter(person__isnull=False).exclude(pk=url_entity.pk).all()

    def clean(self):
        if not self.source.is_internal:
            raise ValidationError(
                "Internal Transfer source must be an internal entity."
            )
        if not self.destination.is_internal:
            raise ValidationError(
                "Internal Transfer destination must be an internal entity."
            )
        return super().clean()
