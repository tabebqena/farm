"""Cash-injection operation proxy.

:class:`CashInjectionOperation` records capital injected into a fund as a
one-shot issuance transaction.
"""

from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import OneShotTransactionMixin, Operation
from apps.app_transaction.transaction_type import TransactionType


class CashInjectionOperation(OneShotTransactionMixin, Operation):
    """Concrete operation proxy for a cash injection.

    Records capital injected from the world into a project fund as a one-shot
    issuance transaction.
    """

    _issuance_transaction_type = TransactionType.CASH_INJECTION_ISSUANCE
    _payment_transaction_type = TransactionType.CASH_INJECTION_PAYMENT

    url_str = "cash-injection"
    label = "Cash Injection"
    _source_role = "world"
    _dest_role = "url"
    theme_color = "success"
    theme_icon = "bi-box-arrow-in-down"

    class Meta:
        proxy = True
        verbose_name = "Cash Injection"

    @property
    def payment_source_fund(self):
        """The world entity acting as the payer."""
        return self.source  # clean_source ensures this is the world entity

    @property
    def payment_target_fund(self):
        """The person/project fund receiving the injection."""
        return self.destination  # clean_destination ensures this is a person

    def clean_source(self):
        """Require the injection source to be the World entity."""
        if not self.source.is_world:
            raise ValidationError("Cash Injection source must be the World entity.")

    def clean_destination(self):
        """Require the injection destination to be a Person entity."""
        if not self.destination.is_person:
            raise ValidationError("Cash Injection must target a Person entity.")
