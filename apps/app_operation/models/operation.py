import logging
from typing import List, Union

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum

from apps.app_base.mixins import (
    AdjustableMixin,
    AmountCleanMixin,
    ImmutableMixin,
    LinkedIssuanceTransactionMixin,
    LinkedPaymentTransactionMixin,
    LinkedRePaymentTransactionMixin,
    OfficerMixin,
)
from apps.app_base.models import BaseModel, ReversableModel
from apps.app_transaction.transaction_type import TransactionType

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Operation Type
# ─────────────────────────────────────────────────────────────────────────────


class OperationType(models.TextChoices):
    CASH_INJECTION = "CASH_INJECTION", "Cash Injection"
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL", "Cash Withdrawal"
    PROJECT_FUNDING = "PROJECT_FUNDING", "Project Funding"
    PROJECT_REFUND = "PROJECT_REFUND", "Project Refund"
    PROFIT_DISTRIBUTION = "PROFIT_DISTRIBUTION", "Profit Distribution"
    LOSS_COVERAGE = "LOSS_COVERAGE", "Loss Coverage"
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER", "Internal Transfer"
    LOAN = "LOAN", "Loan"
    PURCHASE = "PURCHASE", "Purchase"
    SALE = "SALE", "Sale"
    EXPENSE = "EXPENSE", "EXPENSE"
    CAPITAL_GAIN = "CAPITAL_GAIN", "CAPITAL_GAIN"
    CAPITAL_LOSS = "CAPITAL_LOSS", "CAPITAL_LOSS"
    WORKER_ADVANCE = "WORKER_ADVANCE", "WORKER_ADVANCE"

    @classmethod
    def MAP(cls):
        return {
            cls.CASH_INJECTION: {
                "operation_type": cls.CASH_INJECTION,
                "url_str": "cash-injection",
                "source": "world",
                "dest": "url",
                "label": "Cash Injection",
                "can_pay": False,
                "is_partially_payable": False,
                "has_category": False,
                "category_required": False,
                "is_one_shot": True,
                "has_repayment": False,
                "max_payment_count": 1,
            },
            cls.CASH_WITHDRAWAL: {
                "operation_type": cls.CASH_WITHDRAWAL,
                "url_str": "cash-withdrawal",
                "source": "url",
                "dest": "world",
                "label": "Cash Withdrawal",
                "can_pay": False,
                "is_partially_payable": False,
                "has_category": False,
                "category_required": False,
                "is_one_shot": True,
                "has_repayment": False,
                "max_payment_count": 1,
            },
            cls.PROJECT_FUNDING: {
                "operation_type": cls.PROJECT_FUNDING,
                "url_str": "project-funding",
                "source": "url",
                "dest": "post",
                "label": "Project Funding",
                "can_pay": False,
                "is_partially_payable": False,
                "has_category": False,
                "category_required": False,
                "is_one_shot": True,
                "has_repayment": False,
                "max_payment_count": 1,
            },
            cls.PROJECT_REFUND: {
                "operation_type": cls.PROJECT_REFUND,
                "url_str": "project-refunding",
                "source": "post",
                "dest": "url",
                "label": "Project Refund",
                "can_pay": False,
                "is_partially_payable": False,
                "has_category": False,
                "category_required": False,
                "is_one_shot": True,
                "has_repayment": False,
                "max_payment_count": 1,
            },
            cls.PROFIT_DISTRIBUTION: {
                "operation_type": cls.PROFIT_DISTRIBUTION,
                "url_str": "profit-distribution",
                "source": "url",
                "dest": "post",
                "label": "Profit Distribution",
                "can_pay": False,
                "is_partially_payable": False,
                "has_category": False,
                "category_required": False,
                "is_one_shot": True,
                "has_repayment": False,
                "max_payment_count": 1,
            },
            cls.LOSS_COVERAGE: {
                "operation_type": cls.LOSS_COVERAGE,
                "url_str": "loss-coverage",
                "source": "url",
                "dest": "post",
                "label": "Loss Coverage",
                "can_pay": False,
                "is_partially_payable": False,
                "has_category": False,
                "category_required": False,
                "is_one_shot": True,
                "has_repayment": False,
                "max_payment_count": 1,
            },
            cls.INTERNAL_TRANSFER: {
                "operation_type": cls.INTERNAL_TRANSFER,
                "url_str": "internal-transfer",
                "source": "url",
                "dest": "post",
                "label": "Internal Transfer",
                "source_internal": True,
                "dest_internal": True,
                "can_pay": False,
                "is_partially_payable": False,
                "has_category": False,
                "category_required": False,
                "is_one_shot": True,
                "has_repayment": False,
                "max_payment_count": 1,
            },
            cls.LOAN: {
                "operation_type": cls.LOAN,
                "url_str": "loan",
                "source": "url",
                "dest": "post",
                "label": "Debt Issuance",
                "can_pay": False,
                "is_partially_payable": False,
                "has_category": False,
                "category_required": False,
                "is_one_shot": False,
                "has_repayment": True,
                "max_payment_count": -1,
                "repayment_label": "Loan Recovery",  # used in the template
                "repayment_transaction_type": TransactionType.LOAN_REPAYMENT,
            },
            cls.PURCHASE: {
                "operation_type": cls.PURCHASE,
                "url_str": "purchase",
                "source": "url",
                "dest": "post",
                "label": "Purchase Issuance",
                "can_pay": True,
                "is_partially_payable": True,
                "has_category": True,
                "category_required": False,
                "has_invoice": True,
                "is_one_shot": False,
                "has_repayment": False,
                "max_payment_count": -1,
            },
            cls.SALE: {
                "operation_type": cls.SALE,
                "url_str": "sale",
                "source": "post",
                "dest": "url",
                "label": "Sale Issuance",
                "can_pay": True,
                "is_partially_payable": True,
                "has_category": True,
                "category_required": False,
                "has_invoice": True,
                "is_one_shot": False,
                "has_repayment": False,
                "max_payment_count": -1,
            },
            cls.EXPENSE: {
                "operation_type": cls.EXPENSE,
                "url_str": "expense",
                "source": "url",
                "dest": "world",
                "label": "Expense Issuance",
                "can_pay": True,
                "is_partially_payable": True,
                "has_category": True,
                "category_required": True,
                "has_invoice": False,
                "is_one_shot": False,
                "has_repayment": False,
                "max_payment_count": -1,
            },
            cls.CAPITAL_GAIN: {
                "operation_type": cls.CAPITAL_GAIN,
                "url_str": "capital-gain",
                "source": "system",
                "dest": "url",
                "label": "Capital Gain Issuance",
                "can_pay": False,
                "is_partially_payable": False,
                "has_category": False,
                "category_required": False,
                "is_one_shot": True,
                "has_repayment": False,
                "max_payment_count": 1,
            },
            cls.CAPITAL_LOSS: {
                "operation_type": cls.CAPITAL_LOSS,
                "url_str": "capital-loss",
                "source": "url",
                "dest": "system",
                "label": "Capital Loss Issuance",
                "can_pay": False,
                "is_partially_payable": False,
                "has_category": False,
                "category_required": False,
                "is_one_shot": True,
                "has_repayment": False,
                "max_payment_count": 1,
            },
            cls.WORKER_ADVANCE: {
                "operation_type": cls.WORKER_ADVANCE,
                "url_str": "worker-advance",
                "source": "url",
                "dest": "post",
                "label": "Worker Advance Issuance",
                "can_pay": False,
                "is_partially_payable": False,
                "has_category": False,
                "category_required": False,
                "is_one_shot": True,
                "has_repayment": True,
                "max_payment_count": 1,
                "repayment_label": "Advance Repayment",
                "repayment_transaction_type": TransactionType.WORKER_ADVANCE_REPAYMENT,
            },
        }

    @classmethod
    def _url_map(cls) -> dict:
        """Cached reverse lookup: url_str → operation_type."""
        if not hasattr(cls, "_url_map_cache"):
            cls._url_map_cache = {
                config["url_str"]: op_type for op_type, config in cls.MAP().items()
            }
        return cls._url_map_cache

    @classmethod
    def from_url_str(cls, url_str: str) -> str | None:
        return cls._url_map().get(url_str)

    @staticmethod
    def get_canonical_type(url_str_type):
        """Alias for from_url_str — kept for backward compatibility."""
        return OperationType.from_url_str(url_str_type)

    @classmethod
    def get_metadata(cls, op_type) -> dict:
        return cls.MAP().get(op_type, {})

    @staticmethod
    def _is_one_shot_operation(operation_type) -> bool:
        return OperationType.get_metadata(operation_type).get("is_one_shot", False)

    @staticmethod
    def has_repayments(operation_type) -> bool:
        return OperationType.get_metadata(operation_type).get("has_repayment", False)

    @staticmethod
    def max_payment_transaction_count(operation_type) -> int:
        return OperationType.get_metadata(operation_type).get("max_payment_count", 1)

    @staticmethod
    def repayment_label(operation_type) -> Union[str, None]:
        return OperationType.get_metadata(operation_type).get("repayment_label", None)


# ─────────────────────────────────────────────────────────────────────────────
# Operation Manager
# Casts ORM results to the correct proxy subclass automatically
# ─────────────────────────────────────────────────────────────────────────────


class OperationQuerySet(models.QuerySet):
    # Mirrors SafeQuerySet restrictions from app_base
    def update(self, **kwargs):
        raise NotImplementedError(
            "Direct .update() is blocked. Use individual .save() for validation."
        )

    def bulk_create(self, objs, **kwargs):
        raise NotImplementedError(
            "Direct .bulk_create() is blocked. Save objects individually."
        )

    def delete(self):
        from django.conf import settings

        if settings.DEBUG:
            return super().delete()
        raise NotImplementedError("Bulk delete is blocked.")

    def cast(self):
        """
        Re-casts each Operation instance in the queryset to its correct proxy subclass.
        Call this when you need type-specific behavior on query results.
        Usage: Operation.objects.filter(...).cast()
        """
        results = list(self)
        for obj in results:
            proxy_cls = _PROXY_MAP.get(obj.operation_type)
            if proxy_cls:
                obj.__class__ = proxy_cls
        return results


class OperationManager(models.Manager):
    def get_queryset(self):
        return OperationQuerySet(self.model, using=self._db).filter(
            deleted_at__isnull=True
        )

    def cast(self, instance):
        """Cast a single Operation instance to its proxy subclass."""
        print("operation manager cast", instance)
        proxy_cls = _PROXY_MAP.get(instance.operation_type)
        if proxy_cls:
            instance.__class__ = proxy_cls
        return instance


class AllOperationManager(models.Manager):
    """Manager that includes soft-deleted records."""

    def get_queryset(self):
        return OperationQuerySet(self.model, using=self._db)


# ─────────────────────────────────────────────────────────────────────────────
# Base Operation Model  (single DB table)
# ─────────────────────────────────────────────────────────────────────────────


class Operation(
    ImmutableMixin,
    AdjustableMixin,
    AmountCleanMixin,
    LinkedIssuanceTransactionMixin,
    LinkedPaymentTransactionMixin,
    LinkedRePaymentTransactionMixin,
    OfficerMixin,
    ReversableModel,
    BaseModel,
):
    """
    Central financial operation record.
    All type-specific logic lives in proxy subclasses below.
    This class holds only shared fields and shared behavior.
    """

    _immutable_fields = {"source": {}, "destination": {}, "amount": {}}
    _amount_name = "amount"
    _adjustments_related_name = "adjustments"

    source = models.ForeignKey(
        to="app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="operations_outgoing",
    )
    destination = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="operations_incoming",
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    operation_type = models.CharField(max_length=30, choices=OperationType.choices)
    date = models.DateField()
    description = models.TextField(blank=True)
    officer = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="operations_supervised",
    )

    objects = OperationManager()
    all_objects = AllOperationManager()

    class Meta:
        verbose_name = "Operation"
        verbose_name_plural = "Operations"
        ordering = ["-date", "-created_at"]

    # ------------------------------------------------------------------
    # Shared properties
    # ------------------------------------------------------------------

    @property
    def payment_source_fund(self):
        return self.source.fund

    @property
    def payment_target_fund(self):
        return self.destination.fund

    @property
    def _is_one_shot_operation(self):
        return OperationType._is_one_shot_operation(self.operation_type)

    @property
    def has_repayment(self):
        return OperationType.has_repayments(self.operation_type)

    @property
    def max_payment_transaction_count(self):
        return OperationType.max_payment_transaction_count(self.operation_type)

    @property
    def repayment_label(self):
        return OperationType.repayment_label(self.operation_type)

    # ------------------------------------------------------------------
    # Reversal helpers
    # ------------------------------------------------------------------

    @property
    def _reversable_transaction_types(self) -> List[TransactionType]:
        rv = []
        if self._issuance_transaction_type:
            rv.append(self._issuance_transaction_type)
        if self._payment_transaction_type:
            rv.append(self._payment_transaction_type)
        return rv

    @property
    def _implicit_reversable_transaction_types(self) -> List[TransactionType]:
        rv = []
        if self._issuance_transaction_type:
            rv.append(self._issuance_transaction_type)
        if self._is_one_shot_operation and self._payment_transaction_type:
            rv.append(self._payment_transaction_type)
        return rv

    # ------------------------------------------------------------------
    # Cash flow
    # ------------------------------------------------------------------

    def get_cash_flow_balance(self):
        valid_txs = self.get_all_transactions().filter(
            reversal_of__isnull=True,
            reversed_by__isnull=True,
        )
        payment_type = self._payment_transaction_type
        cash_movements = valid_txs.filter(
            Q(type=payment_type) | Q(type=TransactionType.LOAN_REPAYMENT)
        )
        total_payment = (
            cash_movements.filter(type=payment_type).aggregate(Sum("amount"))[
                "amount__sum"
            ]
            or 0
        )
        total_repayment = (
            cash_movements.filter(type=TransactionType.LOAN_REPAYMENT).aggregate(
                Sum("amount")
            )["amount__sum"]
            or 0
        )
        return total_payment - total_repayment

    # ------------------------------------------------------------------
    # Validation — shared rules only
    # Type-specific rules live in proxy clean_source / clean_destination
    # ------------------------------------------------------------------

    def clean(self):
        return super().clean()

    def __str__(self):
        return (
            f"Operation {self.operation_type}: "
            f"{self.amount} from {self.source} to {self.destination}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Proxy Models  — one per operation type
# Each proxy declares its transaction types as plain class attributes
# so the mixin chain reads them without any dict lookup.
# ─────────────────────────────────────────────────────────────────────────────


class CashInjectionOperation(Operation):
    _issuance_transaction_type = TransactionType.CAPITAL_INJECTION_ISSUANCE
    _payment_transaction_type = TransactionType.CAPITAL_INJECTION_PAYMENT

    class Meta:
        proxy = True
        verbose_name = "Cash Injection"

    def clean_source(self):
        if not self.source.is_world:
            raise ValidationError("Cash Injection source must be the World entity.")

    def clean_destination(self):
        if not self.destination.person:
            raise ValidationError("Cash Injection must target a Person entity.")


class CashWithdrawalOperation(Operation):
    _issuance_transaction_type = TransactionType.CAPITAL_WITHDRAWAL_ISSUANCE
    _payment_transaction_type = TransactionType.CAPITAL_WITHDRAWAL_PAYMENT

    class Meta:
        proxy = True
        verbose_name = "Cash Withdrawal"

    def clean_source(self):
        if not self.source.person:
            raise ValidationError("Cash Withdrawal source must be a Person entity.")

    def clean_destination(self):
        if not self.destination.is_world:
            raise ValidationError(
                "Cash Withdrawal destination must be the World entity."
            )


class ProjectFundingOperation(Operation):
    _issuance_transaction_type = TransactionType.PROJECT_FUNDING_ISSUANCE
    _payment_transaction_type = TransactionType.PROJECT_FUNDING_PAYMENT

    class Meta:
        proxy = True
        verbose_name = "Project Funding"

    @property
    def funder(self):
        """The shareholder providing the funds."""
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

    class Meta:
        proxy = True
        verbose_name = "Project Refund"

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

    class Meta:
        proxy = True
        verbose_name = "Profit Distribution"

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

    class Meta:
        proxy = True
        verbose_name = "Loss Coverage"

    @property
    def shareholder(self):
        return self.source

    @property
    def project(self):
        return self.destination


class InternalTransferOperation(Operation):
    _issuance_transaction_type = TransactionType.INTERNAL_TRANSFER_ISSUANCE
    _payment_transaction_type = TransactionType.INTERNAL_TRANSFER_PAYMENT

    class Meta:
        proxy = True
        verbose_name = "Internal Transfer"

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


class LoanOperation(Operation):
    _issuance_transaction_type = TransactionType.LOAN_ISSUANCE
    _payment_transaction_type = TransactionType.LOAN_PAYMENT

    class Meta:
        proxy = True
        verbose_name = "Loan"

    @property
    def creditor(self):
        return self.source

    @property
    def debtor(self):
        return self.destination

    @property
    def _reversable_transaction_types(self) -> List[TransactionType]:
        # Loans must have repayments manually cleared before reversal is allowed.
        return [TransactionType.LOAN_ISSUANCE, TransactionType.LOAN_PAYMENT]

    @property
    def _implicit_reversable_transaction_types(self) -> List[TransactionType]:
        # Only the issuance is implicitly reversed; payments must be cleared manually.
        return [TransactionType.LOAN_ISSUANCE]


class PurchaseOperation(Operation):
    _issuance_transaction_type = TransactionType.PURCHASE_ISSUANCE
    _payment_transaction_type = TransactionType.PURCHASE_PAYMENT

    class Meta:
        proxy = True
        verbose_name = "Purchase"

    @property
    def project(self):
        return self.source

    @property
    def vendor(self):
        return self.destination

    def clean_source(self):
        if not self.source.project:
            raise ValidationError("Purchase source must be a Project entity.")

    def clean_destination(self):
        if not self.destination.is_vendor:
            raise ValidationError("Purchase destination must be a Vendor entity.")


class SaleOperation(Operation):
    _issuance_transaction_type = TransactionType.SALE_ISSUANCE
    _payment_transaction_type = TransactionType.SALE_COLLECTION

    class Meta:
        proxy = True
        verbose_name = "Sale"

    @property
    def project(self):
        return self.destination

    @property
    def client(self):
        return self.source

    def clean_source(self):
        if not self.source.is_client:
            raise ValidationError("Sale source must be a Client entity.")

    def clean_destination(self):
        if not self.destination.project:
            raise ValidationError("Sale destination must be a Project entity.")


class ExpenseOperation(Operation):
    _issuance_transaction_type = TransactionType.EXPENSE_ISSUANCE
    _payment_transaction_type = TransactionType.EXPENSE_PAYMENT

    class Meta:
        proxy = True
        verbose_name = "Expense"

    @property
    def project(self):
        return self.source

    def clean_source(self):
        if not self.source.project:
            raise ValidationError("Expense source must be a Project entity.")

    def clean_destination(self):
        if not self.destination.is_world:
            raise ValidationError("Expense destination must be the World entity.")


class CapitalGainOperation(Operation):
    _issuance_transaction_type = TransactionType.CAPITAL_GAIN_ISSUANCE
    _payment_transaction_type = TransactionType.CAPITAL_GAIN_PAYMENT

    class Meta:
        proxy = True
        verbose_name = "Capital Gain"

    def clean_source(self):
        if not self.source.is_system:
            raise ValidationError("Capital Gain source must be the System entity.")


class CapitalLossOperation(Operation):
    _issuance_transaction_type = TransactionType.CAPITAL_LOSS_ISSUANCE
    _payment_transaction_type = TransactionType.CAPITAL_LOSS_PAYMENT

    class Meta:
        proxy = True
        verbose_name = "Capital Loss"

    def clean_destination(self):
        if not self.destination.is_system:
            raise ValidationError("Capital Loss destination must be the System entity.")


class WorkerAdvanceOperation(Operation):
    _issuance_transaction_type = TransactionType.WORKER_ADVANCE_ISSUANCE
    _payment_transaction_type = TransactionType.WORKER_ADVANCE_PAYMENT
    _repayment_transaction_type = TransactionType.WORKER_ADVANCE_REPAYMENT

    class Meta:
        proxy = True
        verbose_name = "Worker Advance"

    def clean_source(self):
        if not self.source.project:
            raise ValidationError("Worker advance source should be a project.")

    def clean_destination(self):
        if not self.destination.person:
            raise ValidationError("Worker Advance destination must be a person entity.")
        from apps.app_entity.models import Stakeholder

        if not Stakeholder.objects.filter(
            parent=self.source, target=self.destination, active=True
        ).exists():
            raise ValidationError(
                "Worker Advance destination must be an active worker in the selected project."
            )


# ─────────────────────────────────────────────────────────────────────────────
# Proxy Map
# Must be defined AFTER all proxy classes are declared.
# Used by OperationManager.cast() to re-cast ORM results to the correct type.
# ─────────────────────────────────────────────────────────────────────────────

_PROXY_MAP: dict[str, type[Operation]] = {
    OperationType.CASH_INJECTION: CashInjectionOperation,
    OperationType.CASH_WITHDRAWAL: CashWithdrawalOperation,
    OperationType.PROJECT_FUNDING: ProjectFundingOperation,
    OperationType.PROJECT_REFUND: ProjectRefundOperation,
    OperationType.PROFIT_DISTRIBUTION: ProfitDistributionOperation,
    OperationType.LOSS_COVERAGE: LossCoverageOperation,
    OperationType.INTERNAL_TRANSFER: InternalTransferOperation,
    OperationType.LOAN: LoanOperation,
    OperationType.PURCHASE: PurchaseOperation,
    OperationType.SALE: SaleOperation,
    OperationType.EXPENSE: ExpenseOperation,
    OperationType.CAPITAL_GAIN: CapitalGainOperation,
    OperationType.CAPITAL_LOSS: CapitalLossOperation,
    OperationType.WORKER_ADVANCE: WorkerAdvanceOperation,
}


def get_operation_class(operation_type: str) -> Union[type[Operation], None]:
    """
    Factory helper. Returns the correct proxy class for a given operation type.
    Use this when creating operations programmatically.

    Example:
        cls = get_operation_class(OperationType.PURCHASE)
        op = cls.objects.create(operation_type=OperationType.PURCHASE, ...)
    """
    print("get operation class", operation_type)
    return _PROXY_MAP.get(operation_type)
