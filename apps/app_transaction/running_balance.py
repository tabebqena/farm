"""Shared running-balance computation for transaction-ledger style views.

Several views (payment-transactions list, payables/receivables, the period cash
ledger) iterate transactions, classify each one's direction relative to an
entity, and accumulate a running balance. This module centralises that loop so
the duplicated code lives in exactly one place.
"""
from decimal import Decimal

__all__ = ["running_balance_rows"]


def running_balance_rows(transactions, direction_of, initial=Decimal("0.00")):
    """
    Compute a running balance over *transactions*.

    ``direction_of(tx)`` must return ``(direction_label, signed_delta)`` where
    ``signed_delta`` is added to the running balance for that transaction
    (positive adds, negative subtracts).

    Returns a tuple ``(rows, total_in, total_out)``:

    - ``rows``: one ``(tx, direction_label, delta_abs, running_balance)`` per
      transaction, where ``delta_abs`` is the raw ``tx.amount`` and
      ``running_balance`` starts at *initial*.
    - ``total_in``: sum of the *amounts* of positive-delta transactions.
    - ``total_out``: sum of the *amounts* of negative-delta transactions.

    Callers decide how to attach the values (attributes on the tx objects, or
    built into dict rows) and how to label the directions.
    """
    running = initial
    total_in = Decimal("0.00")
    total_out = Decimal("0.00")
    rows = []
    for tx in transactions:
        direction, signed = direction_of(tx)
        running += signed
        if signed > 0:
            total_in += tx.amount
        elif signed < 0:
            total_out += tx.amount
        rows.append((tx, direction, tx.amount, running))
    return rows, total_in, total_out
