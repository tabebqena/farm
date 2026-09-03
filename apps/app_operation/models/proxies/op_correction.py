"""Correction-operation proxy.

:class:`CorrectionOperation` posts a one-shot corrective transaction used to fix
a previously recorded operation's financial effect.
"""

from django.core.exceptions import ValidationError

from apps.app_operation.models.operation import OneShotTransactionMixin, Operation
from apps.app_operation.models.operation_type import OperationType
from apps.app_transaction.transaction_type import TransactionType


class CorrectionOperation(OneShotTransactionMixin, Operation):
    """Single proxy for Correction Credit (system -> project) and Correction
    Debit (project -> system).

    Both operation types share this one proxy class; per-type configuration
    (transaction types, URL slug, label, roles, theme, validation) is dispatched
    on the row's ``operation_type`` via ``_VARIANT_CONFIG``. No behavior differs
    from the two former proxies (CorrectionCreditOperation / CorrectionDebitOperation).
    """

    # One-shot defaults (issuance + single payment at creation, no category, no
    # invoice, not adjustable) come from OneShotTransactionMixin.
    # No balance check: corrections are an admin-only tool to fix wrong calculations;
    # restricting them by fund balance would prevent admins from fixing ledger errors.
    check_balance_on_payment = False

    # Per-type configuration keyed by operation type.
    _VARIANT_CONFIG = {
        OperationType.CORRECTION_CREDIT: {
            "url_str": "correction-credit",
            "label": "Correction Credit",
            "_source_role": "system",
            "_dest_role": "url",
            "_issuance_transaction_type": TransactionType.CORRECTION_CREDIT_ISSUANCE,
            "_payment_transaction_type": TransactionType.CORRECTION_CREDIT_PAYMENT,
            "theme_color": "success",
            "theme_icon": "bi-patch-plus",
            "verbose_name": "Correction Credit",
        },
        OperationType.CORRECTION_DEBIT: {
            "url_str": "correction-debit",
            "label": "Correction Debit",
            "_source_role": "url",
            "_dest_role": "system",
            "_issuance_transaction_type": TransactionType.CORRECTION_DEBIT_ISSUANCE,
            "_payment_transaction_type": TransactionType.CORRECTION_DEBIT_PAYMENT,
            "theme_color": "danger",
            "theme_icon": "bi-patch-minus",
            "verbose_name": "Correction Debit",
        },
    }

    # Both URL slugs resolve to this single proxy class.
    url_strs = ("correction-credit", "correction-debit")

    class Meta:
        proxy = True
        verbose_name = "Correction"

    # ------------------------------------------------------------------
    # Class-level helpers (registry / create-view resolution)
    # ------------------------------------------------------------------

    @classmethod
    def operation_type_for_url(cls, url_str):
        """Return the operation type for a URL slug, or None if unknown."""
        for op_type, cfg in cls._VARIANT_CONFIG.items():
            if cfg["url_str"] == url_str:
                return op_type
        return None

    @classmethod
    def _type_config(cls, operation_type):
        """Per-type config dict used by ``Operation.resolve_request``."""
        return cls._VARIANT_CONFIG.get(operation_type, {})

    # ------------------------------------------------------------------
    # Instance-level per-type dispatch
    # ------------------------------------------------------------------

    def _variant(self):
        """Per-type config dict for this row's operation type."""
        return self._VARIANT_CONFIG[self.operation_type]

    @property
    def _issuance_transaction_type(self):
        """The issuance transaction type for this variant."""
        return self._variant()["_issuance_transaction_type"]

    @property
    def _payment_transaction_type(self):
        """The payment transaction type for this variant."""
        return self._variant()["_payment_transaction_type"]

    @property
    def label(self):
        """Display label for this variant."""
        return self._variant()["label"]

    @property
    def theme_color(self):
        """Bootstrap theme colour for this variant."""
        return self._variant()["theme_color"]

    @property
    def theme_icon(self):
        """Bootstrap icon name for this variant."""
        return self._variant()["theme_icon"]

    @property
    def _source_role(self):
        """How the source entity is resolved for this variant."""
        return self._variant()["_source_role"]

    @property
    def _dest_role(self):
        """How the destination entity is resolved for this variant."""
        return self._variant()["_dest_role"]

    @property
    def payment_source_fund(self):
        """The paying fund: system (credit) or project (debit)."""
        return self.source  # system (credit) or project (debit)

    @property
    def payment_target_fund(self):
        """The receiving fund: project (credit) or system (debit)."""
        return self.destination  # project (credit) or system (debit)

    def clean_source(self):
        """Enforce the correct source entity type for each correction variant."""
        if self.operation_type == OperationType.CORRECTION_CREDIT:
            if not self.source.is_system:
                raise ValidationError(
                    "Correction Credit source must be the System entity."
                )
        else:
            if not self.source.is_project:
                raise ValidationError(
                    "Correction Debit source must be a Project entity."
                )

    def clean_destination(self):
        """Enforce the correct destination entity type for each correction variant."""
        if self.operation_type == OperationType.CORRECTION_CREDIT:
            if not self.destination.is_project:
                raise ValidationError(
                    "Correction Credit destination must be a Project entity."
                )
        else:
            if not self.destination.is_system:
                raise ValidationError(
                    "Correction Debit destination must be the System entity."
                )
