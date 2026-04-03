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

    def clean_destination(self):
        if not self.destination.project:
            raise ValidationError(
                "Project Funding destination must be a Project entity."
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

    def clean_source(self):
        if not self.source.project:
            raise ValidationError("Project Refund source must be a Project entity.")


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
