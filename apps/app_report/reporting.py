"""Computation helpers for the financial report pages.

These helpers compose the model-derived properties (``Entity.balance_at``,
``payables_at``, ``receivables_at``, ``profit_loss`` and the ``FinancialPeriod``
metrics) with targeted ``Transaction`` queries for line-item breakdowns. They
are read-only and must be test-pinned. Formulas follow
``docs/specs/features/financial_reports.md`` §3.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Case, F, Sum, When

from apps.app_inventory.stock import inventory_value
from apps.app_transaction.models import Transaction
from apps.app_transaction.transaction_type import TransactionType

# ---------------------------------------------------------------------------
# Type buckets (spec §3.3–§3.6)
# ---------------------------------------------------------------------------

_INCOME_TYPES = [
    TransactionType.SALE_ISSUANCE,
    TransactionType.CORRECTION_CREDIT_ISSUANCE,
    TransactionType.PURCHASE_ISSUANCE,  # project as vendor
    TransactionType.SALE_ADJUSTMENT_INCREASE,
    TransactionType.PURCHASE_ADJUSTMENT_INCREASE,
]
_INCOME_DECREASE_TYPES = [
    TransactionType.SALE_ADJUSTMENT_DECREASE,
    TransactionType.PURCHASE_ADJUSTMENT_DECREASE,
]
_COST_TYPES = [
    TransactionType.PURCHASE_ISSUANCE,
    TransactionType.EXPENSE_ISSUANCE,
    TransactionType.CORRECTION_DEBIT_ISSUANCE,
    TransactionType.SALE_ISSUANCE,  # project as client
    TransactionType.PURCHASE_ADJUSTMENT_INCREASE,
    TransactionType.SALE_ADJUSTMENT_INCREASE,
    TransactionType.EXPENSE_ADJUSTMENT_INCREASE,
]
_COST_DECREASE_TYPES = [
    TransactionType.PURCHASE_ADJUSTMENT_DECREASE,
    TransactionType.SALE_ADJUSTMENT_DECREASE,
    TransactionType.EXPENSE_ADJUSTMENT_DECREASE,
]

_OPERATING_TYPES = [
    TransactionType.PURCHASE_PAYMENT,
    TransactionType.SALE_COLLECTION,
    TransactionType.EXPENSE_PAYMENT,
]
_FINANCING_TYPES = [
    TransactionType.CASH_INJECTION_PAYMENT,
    TransactionType.CAPITAL_WITHDRAWAL_PAYMENT,
    TransactionType.PROJECT_FUNDING_PAYMENT,
    TransactionType.PROJECT_REFUND_PAYMENT,
    TransactionType.LOAN_PAYMENT,
    TransactionType.LOAN_REPAYMENT,
    TransactionType.WORKER_ADVANCE_PAYMENT,
    TransactionType.WORKER_ADVANCE_REPAYMENT,
    TransactionType.INTERNAL_TRANSFER_PAYMENT,
    TransactionType.CORRECTION_CREDIT_PAYMENT,
    TransactionType.CORRECTION_DEBIT_PAYMENT,
]
_INVESTING_TYPES = []

_CONTRIBUTION_TYPES = [
    TransactionType.CASH_INJECTION_PAYMENT,
    TransactionType.PROJECT_FUNDING_PAYMENT,
]
_WITHDRAWAL_TYPES = [
    TransactionType.CAPITAL_WITHDRAWAL_PAYMENT,
    TransactionType.PROJECT_REFUND_PAYMENT,
]


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _signed_sum(qs):
    """Sum amounts, negating reversal rows (mirrors ``Entity.profit_loss``)."""
    return qs.aggregate(
        total=Sum(
            Case(
                When(reversal_of__isnull=False, then=-F("amount")),
                default=F("amount"),
            )
        )
    )["total"] or Decimal("0.00")


def _plain_sum(qs):
    """Sum amounts as recorded (reversals count with their own sign/direction)."""
    return qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")


def _period_filter(period):
    filters = {"deleted_at__isnull": True, "date__date__gte": period.start_date}
    if period.end_date is not None:
        filters["date__date__lt"] = period.end_date
    return filters


def _signed_by_type(entity, direction, types, tx_valid):
    """Reversal-aware per-type signed sums where *entity* is source/target."""
    qs = Transaction.objects.filter(
        type__in=types,
        **({"target": entity} if direction == "target" else {"source": entity}),
        **tx_valid,
    )
    rows = qs.values("type").annotate(
        total=Sum(
            Case(
                When(reversal_of__isnull=False, then=-F("amount")),
                default=F("amount"),
            )
        )
    )
    return {row["type"]: row["total"] for row in rows if row["total"]}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def income_statement(period):
    """Line-item breakdown of ``Entity.profit_loss`` for *period* (R5)."""
    fund = period.entity
    tx_valid = _period_filter(period)
    income_map = _signed_by_type(
        fund, "target", _INCOME_TYPES + _INCOME_DECREASE_TYPES, tx_valid
    )
    costs_map = _signed_by_type(
        fund, "source", _COST_TYPES + _COST_DECREASE_TYPES, tx_valid
    )

    income = {t: income_map[t] for t in _INCOME_TYPES if income_map.get(t)}
    income_decrease = {
        t: income_map[t] for t in _INCOME_DECREASE_TYPES if income_map.get(t)
    }
    costs = {t: costs_map[t] for t in _COST_TYPES if costs_map.get(t)}
    costs_decrease = {
        t: costs_map[t] for t in _COST_DECREASE_TYPES if costs_map.get(t)
    }

    income_total = sum(
        income_map.get(t, Decimal("0.00")) for t in _INCOME_TYPES
    ) - sum(income_map.get(t, Decimal("0.00")) for t in _INCOME_DECREASE_TYPES)
    costs_total = sum(
        costs_map.get(t, Decimal("0.00")) for t in _COST_TYPES
    ) - sum(costs_map.get(t, Decimal("0.00")) for t in _COST_DECREASE_TYPES)

    return {
        "income": income,
        "income_decrease": income_decrease,
        "costs": costs,
        "costs_decrease": costs_decrease,
        "income_total": income_total,
        "costs_total": costs_total,
        "net": income_total - costs_total,
    }


def balance_sheet(period):
    """Intended full balance sheet as of ``period.as_of`` (R6)."""
    entity = period.entity
    as_of = period.as_of
    cash = entity.balance_at(as_of)
    receivables = entity.receivables_at(as_of)
    inventory = inventory_value(entity, as_of)
    payables = entity.payables_at(as_of)
    assets = cash + receivables + inventory
    liabilities = payables
    return {
        "cash": cash,
        "receivables": receivables,
        "inventory": inventory,
        "assets": assets,
        "payables": payables,
        "liabilities": liabilities,
        "equity": assets - liabilities,
    }


def cash_flow(period):
    """Cash-flow statement for *period* with operating/financing split (R7)."""
    entity = period.entity
    tx_valid = _period_filter(period)

    def category(types):
        incoming = _plain_sum(
            Transaction.objects.filter(target=entity, type__in=types, **tx_valid)
        )
        outgoing = _plain_sum(
            Transaction.objects.filter(source=entity, type__in=types, **tx_valid)
        )
        return {"in": incoming, "out": outgoing, "net": incoming - outgoing}

    opening = period.previous_balance
    closing = entity.balance_at(period.as_of)
    return {
        "opening": opening,
        "operating": category(_OPERATING_TYPES),
        "financing": category(_FINANCING_TYPES),
        "investing": category(_INVESTING_TYPES),
        "net_change": closing - opening,
        "closing": closing,
    }


def _opening_equity(period):
    """Opening equity: cash + inventory + receivables - payables at start - 1 day.

    The day-before is used so opening is a true opening position (the model's
    ``*_previous`` properties are inclusive of the start date).
    """
    entity = period.entity
    day_before = period.start_date - timedelta(days=1)
    if entity.is_project:
        return (
            period.previous_balance
            + inventory_value(entity, day_before)
            + entity.receivables_at(day_before)
            - entity.payables_at(day_before)
        )
    return period.previous_balance


def equity(period):
    """Statement of changes in equity for *period* (R8)."""
    entity = period.entity
    tx_valid = _period_filter(period)
    opening = _opening_equity(period)

    if entity.is_project:
        contributed = _plain_sum(
            Transaction.objects.filter(
                target=entity, type__in=_FINANCING_TYPES, **tx_valid
            )
        ) - _plain_sum(
            Transaction.objects.filter(
                source=entity, type__in=_FINANCING_TYPES, **tx_valid
            )
        )
        retained = income_statement(period)["net"]
        closing = balance_sheet(period)["equity"]
        return {
            "is_project": True,
            "opening": opening,
            "contributed_capital": contributed,
            "retained_earnings": retained,
            "other_changes": closing - opening - contributed - retained,
            "closing": closing,
        }

    contributions = _plain_sum(
        Transaction.objects.filter(
            target=entity, type__in=_CONTRIBUTION_TYPES, **tx_valid
        )
    )
    withdrawals = _plain_sum(
        Transaction.objects.filter(
            source=entity, type__in=_WITHDRAWAL_TYPES, **tx_valid
        )
    )
    closing = entity.balance_at(period.as_of)
    return {
        "is_project": False,
        "opening": opening,
        "contributions": contributions,
        "withdrawals": withdrawals,
        "other_changes": closing - opening - contributions + withdrawals,
        "closing": closing,
    }
