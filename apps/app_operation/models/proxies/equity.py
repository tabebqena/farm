from django.core.exceptions import ValidationError

from apps.app_transaction.transaction_type import TransactionType

from apps.app_operation.models.operation import Operation


class CashInjectionOperation(Operation):
    _issuance_transaction_type = TransactionType.CAPITAL_INJECTION_ISSUANCE
    _payment_transaction_type = TransactionType.CAPITAL_INJECTION_PAYMENT

    url_str = "cash-injection"
    label = "Cash Injection"
    _source_role = "world"
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
        verbose_name = "Cash Injection"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean_source ensures this is the world entity

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean_destination ensures this is a person

    def clean_source(self):
        if not self.source.is_world:
            raise ValidationError("Cash Injection source must be the World entity.")

    def clean_destination(self):
        if not self.destination.person:
            raise ValidationError("Cash Injection must target a Person entity.")


class CashWithdrawalOperation(Operation):
    _issuance_transaction_type = TransactionType.CAPITAL_WITHDRAWAL_ISSUANCE
    _payment_transaction_type = TransactionType.CAPITAL_WITHDRAWAL_PAYMENT

    url_str = "cash-withdrawal"
    label = "Cash Withdrawal"
    _source_role = "url"
    _dest_role = "world"
    can_pay = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1

    class Meta:
        proxy = True
        verbose_name = "Cash Withdrawal"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean_source ensures this is a person

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean_destination ensures this is the world entity

    def clean_source(self):
        if not self.source.person:
            raise ValidationError("Cash Withdrawal source must be a Person entity.")

    def clean_destination(self):
        if not self.destination.is_world:
            raise ValidationError(
                "Cash Withdrawal destination must be the World entity."
            )


class CapitalGainOperation(Operation):
    _issuance_transaction_type = TransactionType.CAPITAL_GAIN_ISSUANCE
    _payment_transaction_type = TransactionType.CAPITAL_GAIN_PAYMENT

    url_str = "capital-gain"
    label = "Capital Gain Issuance"
    _source_role = "system"
    _dest_role = "url"
    can_pay = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1

    class Meta:
        proxy = True
        verbose_name = "Capital Gain"

    @property
    def payment_source_fund(self):
        return self.source.fund  # clean_source ensures this is the system entity

    @property
    def payment_target_fund(self):
        return self.destination.fund  # entity receiving the gain

    def clean_source(self):
        if not self.source.is_system:
            raise ValidationError("Capital Gain source must be the System entity.")


class CapitalLossOperation(Operation):
    _issuance_transaction_type = TransactionType.CAPITAL_LOSS_ISSUANCE
    _payment_transaction_type = TransactionType.CAPITAL_LOSS_PAYMENT

    url_str = "capital-loss"
    label = "Capital Loss Issuance"
    _source_role = "url"
    _dest_role = "system"
    can_pay = False
    is_partially_payable = False
    has_category = False
    category_required = False
    _is_one_shot_operation = True
    has_repayment = False
    max_payment_transaction_count = 1

    class Meta:
        proxy = True
        verbose_name = "Capital Loss"

    @property
    def payment_source_fund(self):
        return self.source.fund  # entity absorbing the loss

    @property
    def payment_target_fund(self):
        return self.destination.fund  # clean_destination ensures this is the system entity

    def clean_destination(self):
        if not self.destination.is_system:
            raise ValidationError("Capital Loss destination must be the System entity.")
