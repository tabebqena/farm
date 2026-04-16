# EPIC 1 — Fund & Transaction Core
> Foundational infrastructure. All other epics depend on this being correct.

---

### Feature 1.1 — Fund Balance Computation
**Goal:** `fund.balance` returns the correct net value of a fund at any point.

Tasks:
- [x] Add `balance` property to `Fund` model: sums payment-type transactions in vs out, excluding deleted transactions (implemented as `balance_at(date.today())`)
- [x] Add `balance_at(dt)` method for historical balance queries (note: implemented as `balance_at`, not `balance_as_of`)
- [x] Add `assets_at(dt)` method covering cash + receivables + inventory + loans + advances
- [ ] Write dedicated unit tests: empty fund = 0, injection increases balance, withdrawal decreases it

---

### Feature 1.2 — Transaction.clean() Validation
**Goal:** ~~The `Transaction.clean()` method currently blocks all transactions with a wrong check. Fix it.~~

**Status: Approach changed.** Validation is now done at the Operation proxy model level (`clean_source`, `clean_destination`, `clean` on each proxy). The `Transaction.clean_type()` method remains a stub (`...`). The `DOCUMENT_TYPE_MAP` approach was abandoned in favour of per-proxy validation.

Tasks:
- [x] Remove the bad `DOCUMENT_TYPE_MAP` guard in `Transaction.clean()` — done (guard removed, `clean_type` is now a stub)
- ~~[ ] Expand `DOCUMENT_TYPE_MAP` to include all 14 operation types~~ — cancelled; validation lives in proxy models
- ~~[ ] Re-enable `clean_type()` body~~ — cancelled; validation lives in proxy models
- ~~[ ] Write a test that saves a `PURCHASE_PAYMENT` transaction on a `PURCHASE` operation~~ — cancelled; covered by Purchase proxy model tests

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
