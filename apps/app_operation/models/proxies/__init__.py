from typing import Union

from apps.app_operation.models.operation import Operation
from apps.app_operation.models.operation_type import OperationType

from .op_capital_gain import CapitalGainOperation
from .op_correction_credit import CorrectionCreditOperation
from .op_correction_debit import CorrectionDebitOperation
from .op_capital_loss import CapitalLossOperation
from .op_cash_injection import CashInjectionOperation
from .op_cash_withdrawal import CashWithdrawalOperation
from .op_expense import ExpenseOperation
from .op_internal_transfer import InternalTransferOperation
from .op_loan import LoanOperation
from .op_loss_coverage import LossCoverageOperation
from .op_profit_distribution import ProfitDistributionOperation
from .op_project_funding import ProjectFundingOperation
from .op_project_refund import ProjectRefundOperation
from .op_purchase import PurchaseOperation
from .op_sale import SaleOperation
from .op_worker_advance import WorkerAdvanceOperation

PROXY_MAP: dict[str, type[Operation]] = {
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
    OperationType.CORRECTION_CREDIT: CorrectionCreditOperation,
    OperationType.CORRECTION_DEBIT: CorrectionDebitOperation,
    OperationType.WORKER_ADVANCE: WorkerAdvanceOperation,
}

# Reverse lookup: url_str → proxy class
_URL_MAP: dict[str, type[Operation]] = {
    proxy_cls.url_str: proxy_cls for proxy_cls in PROXY_MAP.values()
}


def get_canonical_type(url_str: str) -> type[Operation] | None:
    """
    Resolves a URL string to the corresponding proxy class.
    The proxy class carries all operation config (label, can_pay, etc.)
    as well as the transaction types and business logic.

    Example:
        proxy_cls = get_canonical_type("purchase")
        print(proxy_cls.label)   # "Purchase Issuance"
        print(proxy_cls.can_pay) # True
    """
    return _URL_MAP.get(url_str)


def get_operation_class(operation_type: str) -> Union[type[Operation], None]:
    """
    Factory helper. Returns the correct proxy class for a given operation type.
    Use this when creating operations programmatically.

    Example:
        cls = get_operation_class(OperationType.PURCHASE)
        op = cls.objects.create(operation_type=OperationType.PURCHASE, ...)
    """
    return PROXY_MAP.get(operation_type)


__all__ = [
    "PROXY_MAP",
    "get_canonical_type",
    "get_operation_class",
    "CashInjectionOperation",
    "CashWithdrawalOperation",
    "CapitalGainOperation",
    "CapitalLossOperation",
    "CorrectionCreditOperation",
    "CorrectionDebitOperation",
    "ProjectFundingOperation",
    "ProjectRefundOperation",
    "ProfitDistributionOperation",
    "LossCoverageOperation",
    "InternalTransferOperation",
    "LoanOperation",
    "WorkerAdvanceOperation",
    "PurchaseOperation",
    "SaleOperation",
    "ExpenseOperation",
]
