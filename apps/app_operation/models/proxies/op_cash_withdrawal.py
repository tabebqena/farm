"""Cash-withdrawal operation proxy.

:class:`CashWithdrawalOperation` records capital taken out of a fund as a
one-shot transaction.
"""

from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import OneShotTransactionMixin, Operation
from apps.app_transaction.transaction_type import TransactionType


class CashWithdrawalOperation(OneShotTransactionMixin, Operation):
    """Concrete operation proxy for a cash withdrawal.

    Records capital taken out of a project fund back to the world as a one-shot
    transaction (the fund's balance is checked at payment time).
    """

    _issuance_transaction_type = TransactionType.CAPITAL_WITHDRAWAL_ISSUANCE
    _payment_transaction_type = TransactionType.CAPITAL_WITHDRAWAL_PAYMENT

    url_str = "cash-withdrawal"
    label = "Cash Withdrawal"
    _source_role = "url"
    _dest_role = "world"
    check_balance_on_payment = True

    class Meta:
        proxy = True
        verbose_name = "Cash Withdrawal"

    @property
    def payment_source_fund(self):
        """The person/project fund being debited."""
        return self.source  # clean_source ensures this is a person

    @property
    def payment_target_fund(self):
        """The world entity receiving the withdrawn capital."""
        return self.destination  # clean_destination ensures this is the world entity

    def clean_source(self):
        """Require the withdrawal source to be a Person entity."""
        if not self.source.is_person:
            raise ValidationError("Cash Withdrawal source must be a Person entity.")

    def clean_destination(self):
        """Require the withdrawal destination to be the World entity."""
        if not self.destination.is_world:
            raise ValidationError(
                "Cash Withdrawal destination must be the World entity."
            )
