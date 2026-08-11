# Plan: Display Payables, Receivables & Stock Value on Entity Detail Page

## Goal
Show an entity's outstanding payables, receivables, and stock value directly on the
entity detail page, and let the user drill into the transactions that build up the
payables figure.

## Decisions
- Payables / receivables are sourced from the existing `Entity.payables` /
  `Entity.receivables` properties (which delegate to `payables_at` / `receivables_at`).
- Stock value is sourced from `ProductLedgerEntry.inventory_value_at(entity, today)`
  (net book value of on-hand inventory; zero for entities without inventory).
- Currency uses `settings.CURRENCY_SYMBOL`.

## Implemented

### View: `apps/app_entity/views/entity_detail.py`
- Added `payables`, `receivables`, `stock_value`, and `currency` to the context of
  `entity_detail_view`.

### Template: `apps/app_entity/templates/app_entity/entity_detail.html`
- Added a "Financial Summary" card in the left column (below Current Fund Balance):
  - Current Balance -> links to the payment transactions list
  - Payables -> links to the new payables page
  - Receivables -> links to the new receivables page
  - Stock Value -> links to stock detail (projects only)

### Payables page
- New view `entity_payables_view` in `apps/app_transaction/views.py`:
  - Lists the issuance/payment/adjustment transactions that increase or decrease
    payables (mirrors `Entity.payables_at` type sets), excluding transactions already
    reversed as of today.
  - Annotates each row with `direction` (`increase` / `decrease`) and a running
    payable balance; exposes `total_increase`, `total_decrease`, `current_obligation`.
  - Paginated (25 per page), running balance computed over all rows first.
- New URL `entity/<int:entity_pk>/payables/` named `entity_payables_list` in
  `apps/app_transaction/urls.py`.
- New template `apps/app_transaction/templates/app_transaction/entity_payables.html`.

### Receivables page
- New view `entity_receivables_view` (mirrors payables, uses `Entity.receivables_at`
  type sets) with URL `entity/<int:entity_pk>/receivables/` named
  `entity_receivables_list`.
- New template `apps/app_transaction/templates/app_transaction/entity_receivables.html`.

### Shared helper
- Refactored the payables/receivables transaction building into
  `_build_obligation_transactions` and the shared page renderer `_obligation_context`
  in `apps/app_transaction/views.py` to avoid duplication.

### Rename: transactions list -> Payment Transactions
- URL name `entity_transactions_list` -> `entity_payment_transactions_list`; view
  `entity_transactions_view` -> `entity_payment_transactions_view`; template
  `entity_transactions.html` -> `entity_payment_transactions.html`.
- Page title/heading now read "Payment Transactions" / "Payment Transactions List".
- Navigation entry renamed and updated in `apps/app_base/navigation.py`; payables and
  receivables navigation entries added.

## Tests
- `apps/app_entity/tests/test_views_get_entity_detail_view.py`:
  - context exposes payables/receivables/stock_value/currency
  - payables reflected from an expense issuance
  - stock value reflected from a product ledger entry
  - financial summary card renders balance plus the payables and receivables links
- `apps/app_transaction/tests.py`:
  - `EntityPayablesViewTests`:
    - authorized user loads page
    - issuance increases / payment decreases running payables + totals
    - non-payable transactions (e.g. CAPITAL_GAIN_PAYMENT) excluded
    - 404 for missing entity, redirect for unauthenticated
    - pagination (25 per page, page 2 works)
  - `EntityReceivablesViewTests`:
    - authorized user loads page
    - worker advance increases / repayment decreases running receivables + totals
    - non-receivable transactions (e.g. CAPITAL_GAIN_PAYMENT) excluded
    - 404 for missing entity, redirect for unauthenticated
    - pagination (25 per page, page 2 works)
  - `EntityTransactionsViewTests` updated for the renamed URL.

## Verification
- `python manage.py test apps.app_transaction apps.app_entity` -> 144 passed
- `python manage.py test apps.app_transaction` -> 59 passed
- `python manage.py test apps.app_entity` -> 85 passed
- `python manage.py check` -> no issues
