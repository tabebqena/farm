from typing import Union

from apps.app_operation.models.operation import Operation
from apps.app_operation.models.operation_type import OperationType

from .op_birth import BirthOperation
from .op_consumption import ConsumptionOperation
from .op_capital_valuation import CapitalValuationOperation
from .op_death import DeathOperation
from .op_correction import CorrectionOperation
from .op_cash_injection import CashInjectionOperation
from .op_cash_withdrawal import CashWithdrawalOperation
from .op_expense import ExpenseOperation
from .op_internal_transfer import InternalTransferOperation
from .op_loan import LoanOperation
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
    OperationType.INTERNAL_TRANSFER: InternalTransferOperation,
    OperationType.LOAN: LoanOperation,
    OperationType.PURCHASE: PurchaseOperation,
    OperationType.SALE: SaleOperation,
    OperationType.EXPENSE: ExpenseOperation,
    OperationType.BIRTH: BirthOperation,
    OperationType.DEATH: DeathOperation,
    OperationType.CAPITAL_GAIN: CapitalValuationOperation,
    OperationType.CAPITAL_LOSS: CapitalValuationOperation,
    OperationType.CORRECTION_CREDIT: CorrectionOperation,
    OperationType.CORRECTION_DEBIT: CorrectionOperation,
    OperationType.WORKER_ADVANCE: WorkerAdvanceOperation,
    OperationType.CONSUMPTION: ConsumptionOperation,
}

# Reverse lookup: slug → proxy class. A single proxy may register several slugs
# (e.g. CorrectionOperation serves both "correction-credit" and "correction-debit").
_URL_MAP: dict[str, type[Operation]] = {}
for _proxy_cls in PROXY_MAP.values():
    _slugs = getattr(_proxy_cls, "url_strs", None) or (_proxy_cls.url_str,)
    for _slug in _slugs:
        if _slug:
            _URL_MAP[_slug] = _proxy_cls


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
    "BirthOperation",
    "DeathOperation",
    "CashInjectionOperation",
    "CashWithdrawalOperation",
    "CapitalValuationOperation",
    "CorrectionOperation",
    "ProjectFundingOperation",
    "ProjectRefundOperation",
    "InternalTransferOperation",
    "LoanOperation",
    "WorkerAdvanceOperation",
    "PurchaseOperation",
    "SaleOperation",
    "ExpenseOperation",
    "ConsumptionOperation",
]
