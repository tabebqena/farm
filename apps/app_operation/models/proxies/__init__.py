from typing import Union

from apps.app_operation.models.operation import Operation
from apps.app_operation.models.operation_type import OperationType

from .allocation import (
    InternalTransferOperation,
    LossCoverageOperation,
    ProfitDistributionOperation,
    ProjectFundingOperation,
    ProjectRefundOperation,
)
from .credit import LoanOperation, WorkerAdvanceOperation
from .equity import (
    CapitalGainOperation,
    CapitalLossOperation,
    CashInjectionOperation,
    CashWithdrawalOperation,
)
from .trade import ExpenseOperation, PurchaseOperation, SaleOperation

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
