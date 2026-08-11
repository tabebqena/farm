# Operations List View — Appearance & UX Improvement

## Goal
Improve the operations list page ([`operation_list.html`](../apps/app_operation/templates/app_operation/operation_list.html)) so it:

1. Displays the entity's **current fund balance** in a dedicated card.
2. Removes the **"Customize Columns"** feature — every column is required, so toggling adds
   clutter and hides important data.
3. Is **mobile friendly** — the row layout stacks cleanly on small screens with clear labels.
4. Shows **operation, paid, remaining, and totally settled** using a user-friendly pattern
   (labeled values, status badges, and a settlement progress bar) instead of cryptic
   `P: / R:` badges.

## Data model notes
- `Operation` inherits payment/repayment mixins from `apps/app_base/mixins.py`:
  - `amount_settled`, `amount_remaining_to_settle`, `is_fully_settled` (payment semantics).
  - `amount_repayed`, `amount_remaining_to_repay`, `is_fully_repayed` (repayment semantics).
  - `effective_amount` (amount after adjustments) — the operation total.
- Operations flagged `has_repayment` (Loan, Worker Advance) should use **repayment**
  semantics for the display (paid = repaid, remaining = still owed).
- All other operations use **settlement** semantics (paid = settled amount).
- `entity.balance` provides the current fund balance.
- Currency symbol comes from `settings.CURRENCY_SYMBOL` (default `$`), consistent with
  other views.

## Changes
### 1. View — `apps/app_operation/views/list.py`
- Add `currency` to the context (`settings.CURRENCY_SYMBOL`).
- Precompute a display list of dicts:
  - `operation` — the proxy instance.
  - `paid`, `remaining`, `total`, `fully_settled`, `percent` (for the progress bar).
  - For `has_repayment` operations use repayment fields; otherwise settlement fields.
- Paginate the display list so pagination reflects enriched rows.

### 2. Template — `apps/app_operation/templates/app_operation/operation_list.html`
- Add a **Current Balance** card above the operations list.
- Remove the column legend + "Customize Columns" toggle panel, the `data-column`
  attributes, the toggle JS, and the related `extra_css`.
- Rebuild each row as a responsive layout:
  - Identity: IN/OUT badge, operation type, date, counterparty.
  - Amount (signed, color-coded).
  - Paid and Remaining with inline labels on mobile.
  - Status badge: Reversed / Reversal / Fully Settled / Partially Paid / Unpaid.
  - Settlement progress bar.
  - View/Edit action buttons.
- Keep existing pagination and empty state.

## Verification
- `python manage.py check`
- `pytest apps/app_operation/tests/views/test_views_get_operation_list_view.py`

## Implementation notes (executed)
- [`apps/app_operation/views/list.py`](../apps/app_operation/views/list.py):
  - Enriched each operation into a display dict with `operation`, `kind`, `paid`,
    `remaining`, `total`, `fully_settled`, `percent` (progress bar value).
  - Classifies every operation into one of three kinds:
    - `one_shot` — `is_partially_payable=False` and `has_repayment=False`; settled in
      full at creation (`paid = total`, `remaining = 0`).
    - `paid` — `is_partially_payable=True` (purchase, sale, expense); uses
      `amount_settled` / `amount_remaining_to_settle` / `is_fully_settled`.
    - `repayed` — `has_repayment=True` (loan, worker advance); uses
      `amount_repayed` / `amount_remaining_to_repay` / `is_fully_repayed`.
  - Remaining is clamped to non-negative; percent is capped at 100.
  - Context now includes `balance` (entity current fund balance) and `currency`
    (`settings.CURRENCY_SYMBOL`, default `$`).
- [`apps/app_operation/templates/app_operation/operation_list.html`](../apps/app_operation/templates/app_operation/operation_list.html):
  - Added a **Current Balance** card (color-coded by sign) with a link to the entity's
    payment transactions.
  - Removed the "Customize Columns" button, legend, `data-column` attributes, and the
    column-toggle JS/CSS — all columns are always shown.
  - Reworked each row into a responsive layout: IN/OUT + type + date + counterparty,
    signed color-coded amount, and a kind-aware status badge:
    - Reversed / Reversal (red), `one_shot` → **Settled**, fully paid → **Fully Paid**,
      fully repaid → **Fully Repaid**, partial → **Partially Paid / Partially Repaid**,
      none → **Unpaid / Unrepaid**.
  - **Paid / Repaid** and **Remaining** columns use kind-appropriate labels ("Paid" vs
    "Repaid") and show `—` for reversed/reversal entries; the settlement progress bar is
    shown only for `paid` / `repayed` operations (one-shot rows stay clean).
  - Kept pagination and empty state unchanged.
- [`apps/app_operation/tests/views/test_views_get_operation_list_view.py`](../apps/app_operation/tests/views/test_views_get_operation_list_view.py):
  - Added `test_operation_list_enriches_settlement_values_and_balance` covering the new
    context keys (including `kind`) and enriched row fields.

## Test results
- `manage.py check` — no issues.
- `manage.py test apps.app_operation.tests.views --parallel=8` — 45 passed.
  (Note: pytest-django is not installed; tests run via Django's test runner per the repo
  convention.)
