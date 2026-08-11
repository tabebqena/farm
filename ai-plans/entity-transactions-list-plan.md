# Entity Transactions List (Balance Tracking)

## Goal
Provide a page that lists all payment (cash-flow) transactions related to an
entity, filtered to balance-affecting transaction types, so the fund balance can
be tracked over time.

## Design
- A single view `entity_transactions_view` under `apps/app_transaction` accepts
  an `entity_pk`.
- It queries `Transaction` rows where the entity is `source` (outgoing) or
  `target` (incoming) and `type` is in `TransactionType.payment_types()`.
  Issuance transactions (obligations/receivables that do not move cash) are
  excluded — they do not affect the fund balance.
- Each row is annotated with:
  - `direction`: `incoming` (target) or `outgoing` (source)
  - `running_balance`: cumulative balance after that transaction
    (incoming `+amount`, outgoing `-amount`), matching `Entity.balance_at()`.
- Summary cards show current balance, total incoming, total outgoing, and
  transaction count.
- The annotated list is paginated (25 per page) using Django's `Paginator`.
  Running balances are computed over ALL rows first, so they stay correct
  across pages.

## Files changed / added
- `apps/app_transaction/views.py` — added `entity_transactions_view`.
- `apps/app_transaction/urls.py` — added
  `transactions/entity/<int:entity_pk>/` → `entity_transactions_list`.
- `apps/app_transaction/templates/app_transaction/entity_transactions.html` —
  new template (summary cards + transactions table + pagination).
- `apps/app_base/navigation.py` — added nav entry for `entity_transactions_list`.
- `apps/app_entity/templates/app_entity/entity_detail.html` — added
  "Transactions" button in the header and "View Transactions" link in the
  fund-balance card.
- `apps/app_transaction/tests.py` — added `EntityTransactionsViewTests`
  (8 tests: access, payment-only filter, directions, running balance/totals,
  entity scoping, 404, auth redirect, pagination).

## Verification
- `python manage.py check` — no issues.
- `python manage.py test --parallel=8 apps.app_transaction
  apps.app_entity.tests.test_views_get_entity_detail_view` — 44 tests OK.
