# EPIC 1 — Fund & Transaction Core
> Foundational infrastructure. All other epics depend on this being correct.

---

### Feature 1.1 — Fund Balance Computation
**Goal:** `fund.balance` returns the correct net value of a fund at any point.

Tasks:
- [ ] Add `balance` property to `Fund` model: sum of `transactions_incoming.amount` minus `transactions_outgoing.amount`, excluding reversed/reversal transactions
- [ ] Add `balance_as_of(date)` method for historical balance queries
- [ ] Write unit tests: empty fund = 0, injection increases balance, withdrawal decreases it, reversed tx is excluded

---

### Feature 1.2 — Transaction.clean() Validation
**Goal:** The `Transaction.clean()` method currently blocks *all* transactions with a wrong check. Fix it.

Tasks:
- [*] Remove or fix the `DOCUMENT_TYPE_MAP` guard in `Transaction.clean()` — currently raises `ValidationError` for all valid operation types
- [ ] Expand `DOCUMENT_TYPE_MAP` to include all 14 operation types and their allowed transaction types (use `OperationType.MAP()` as source of truth)
- [ ] Re-enable `clean_type()` body (currently has an early `return` that skips all validation)
- [ ] Write a test that saves a `PURCHASE_PAYMENT` transaction on a `PURCHASE` operation — should pass

---

### Feature 1.3 — Ledger History Tab + Shared Payment Views
**Goal:** The entity detail page has a "Ledger History" tab that currently says "coming soon". Make it real. Also fix the broken shared payment/repayment views.

Tasks:
- [ ] Add a view that returns all transactions for a given entity's fund (both incoming and outgoing)
- [ ] Wire the view into `entity_detail.html`
- [ ] Show: date, type, amount, direction (in/out), counterparty fund, linked document
- [ ] Paginate — 25 rows per page
- [ ] Fix fund direction in `record_transaction_payment`: `source=operation.source.fund`, `target=operation.destination.fund`
- [ ] Remove the dead `operation.create_payment_transaction` line (called without parentheses)
- [ ] Verify `record_transaction_repayment` fund direction is correct: repayment flows `destination.fund → source.fund`
- [ ] Verify the `amount_remaining_to_repay` property exists on proxy models that use repayment (LOAN, WORKER_ADVANCE)
- [ ] Manual test: record a payment on a PURCHASE — funds should move project → vendor
