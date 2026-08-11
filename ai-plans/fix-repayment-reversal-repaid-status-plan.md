# Fix: Operation still shows "Fully Repaid" after a repayment transaction is reversed

## Problem statement

For repayable operations (worker advance, loan):

1. Record a full repayment so the operation is marked "Fully Repaid".
2. Reverse that repayment transaction (mirror-image reversal via the transaction detail page).
3. The operation **still shows Fully Repaid** in both the operation detail view and the operation list view, and the "Remaining to Repay" amount stays at 0.

## Root cause

The repaid amount is computed by
[`LinkedRePaymentTransactionMixin.amount_repayed`](apps/app_base/mixins.py:480) in
`apps/app_base/mixins.py`:

```python
@property
def amount_repayed(self):
    valid_txs = self.get_undeleted_transactions()
    if not valid_txs:
        return Decimal("0")
    if hasattr(self, "_repayment_transaction_type"):
        valid_txs = valid_txs.filter(type=self._repayment_transaction_type)
    to_source = valid_txs.filter(target=self.payment_source_fund).aggregate(
        total=Sum(self._tx_amount_field_name)
    )["total"] or Decimal("0.00")
    return to_source
```

It sums **only** transactions where `target == payment_source_fund` (money flowing
into the source fund). It never subtracts money flowing **out** of the source fund.

When a repayment transaction `R` (e.g. worker -> project) is reversed through
[`Transaction.reverse()`](apps/app_transaction/models.py:274):

- A mirror reversal `R'` (project -> worker) is created with `reversal_of=R`; `R`
  becomes `reversed_by=R'`.
- `R` still has `target == payment_source_fund`, so it **keeps counting** toward
  `amount_repayed`.
- `R'` has `target == worker`, so it is **not counted** at all (and there is no
  offset term to subtract it).

Net effect: `amount_repayed` is unchanged after reversing a repayment, so
`is_fully_repayed` stays `True` and `amount_remaining_to_repay` stays `0`.

Both views then render the stale value:

- Detail: [`invoice_repayment_summary.html`](apps/app_operation/templates/app_operation/snippets/detail/invoice_repayment_summary.html:96)
  displays `operation.amount_repayed` and `operation.is_fully_repayed`.
- List: [`operation_list_view`](apps/app_operation/views/list.py:63) uses
  `op.amount_repayed`, `op.amount_remaining_to_repay`, `op.is_fully_repayed`.

### Why payments do not have this bug

The parallel payment property
[`LinkedPaymentTransactionMixin.amount_settled`](apps/app_base/mixins.py:271)
computes a **net** value:

```python
to_receiver = valid_txs.filter(target=self.payment_target_fund)...
from_receiver = valid_txs.filter(source=self.payment_target_fund)...
return to_receiver - from_receiver
```

The reversal mirror `P'` has `source == payment_target_fund`, so it is subtracted
via `from_receiver` and the reversal cancels out. `amount_repayed` is the
one-directional variant that lost this offset term.

## Fix

Make `amount_repayed` mirror `amount_settled` by subtracting repayment-type money
flowing out of the source fund:

```python
@property
def amount_repayed(self):
    valid_txs = self.get_undeleted_transactions()
    if not valid_txs:
        return Decimal("0")
    if hasattr(self, "_repayment_transaction_type"):
        valid_txs = valid_txs.filter(type=self._repayment_transaction_type)
    to_source = valid_txs.filter(target=self.payment_source_fund).aggregate(
        total=Sum(self._tx_amount_field_name)
    )["total"] or Decimal("0.00")
    from_source = valid_txs.filter(source=self.payment_source_fund).aggregate(
        total=Sum(self._tx_amount_field_name)
    )["total"] or Decimal("0.00")
    return to_source - from_source
```

Why this is safe:

- Legitimate repayment transactions always flow `payment_target_fund -> payment_source_fund`
  (see [`create_repayment_transaction`](apps/app_base/mixins.py:527)), so they never
  appear in `from_source`.
- The only repayment-type transactions with `source == payment_source_fund` are the
  mirror reversals, so `from_source` exactly offsets reversed repayments.

Equivalent alternative (semantically identical, matches the existing pattern in
[`WorkerAdvanceOperation._requires_transaction_reversal`](apps/app_operation/models/proxies/op_worker_advance.py:82)):
filter `valid_txs` with `reversal_of__isnull=True, reversed_by__isnull=True` instead
of adding the `from_source` term. Prefer the net approach for consistency with
`amount_settled`.

## Why the test suite did not catch this bug

The suite tests repayment accounting and transaction reversal **in isolation**,
but never the combination "repayment recorded -> repayment reversed -> repaid-state
asserted":

- Repayment tests ([`test_worker_advance_worker_advance_repayment.py`](apps/app_operation/tests/operations/worker/test_worker_advance_worker_advance_repayment.py),
  [`test_loan_loan_repayment.py`](apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py))
  only cover the happy path: record repayments -> remaining decreases -> fully
  repaid. They never reverse a repayment.
- The only place a repayment is reversed in the whole suite is
  [`test_loan_loan_reversal.py`](apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py:142)
  (`test_reversal_allowed_when_repayment_is_reversed`), and there it is reversed
  only to enable **operation-level** reversal; the repaid-state after the
  transaction reversal is never inspected.
- Transaction reversal tests ([`apps/app_transaction/tests.py`](apps/app_transaction/tests.py))
  exercise `Transaction.reverse()` mechanics on standalone transactions (mirror
  creation, swapped source/target, reversal guards) and never assert downstream
  operation accounting.
- View tests ([`test_views_get_operation_detail_view.py`](apps/app_operation/tests/views/test_views_get_operation_detail_view.py:227))
  assert the "Record Repayment" link from `is_fully_repayed` for freshly-repaid
  and partially-repaid states only, never the post-reversal state.

Because the bug only manifests as a stale repaid amount after a repayment
reversal, and no test asserts that state, nothing failed. The asymmetry between
the net-based `amount_settled` and the one-directional `amount_repayed` is also
silent: `amount_settled` is correct by construction, so no payment test would
flag the divergence either.

## Tests

Add regression tests that reverse a full repayment and assert the repaid/remaining
state is restored:

1. [`test_worker_advance_worker_advance_repayment.py`](apps/app_operation/tests/operations/worker/test_worker_advance_worker_advance_repayment.py)
   - Full repayment (1000) -> `is_fully_repayed` True.
   - Reverse the repayment transaction -> assert `is_fully_repayed` is False,
     `amount_repayed` is 0, `amount_remaining_to_repay` is back to 1000.
   - Also cover a partial scenario: repay 400 of 1000, reverse it -> remaining back
     to 1000.
2. [`test_loan_loan_repayment.py`](apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py)
   - Same two scenarios for `LoanOperation` (the mixin is shared, but both proxies
     must stay green).
3. View-level (optional but recommended):
   - [`test_views_get_operation_detail_view.py`](apps/app_operation/tests/views/test_views_get_operation_detail_view.py)
     and the operation list view test: after reversing the repayment, the response
     no longer contains the "Fully Repaid" label and shows a nonzero remaining amount.

## Verification

- `python manage.py check`
- Targeted pytest for the changed area:
  - `pytest apps/app_operation/tests/operations/worker/test_worker_advance_worker_advance_repayment.py`
  - `pytest apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py`
  - `pytest apps/app_operation/tests/views/` (for the view-level regression)
- Per project rule, parallel test runs use `manage.py test --parallel=8`.

## Files touched

- `apps/app_base/mixins.py` — fix `LinkedRePaymentTransactionMixin.amount_repayed`
- `apps/app_operation/tests/operations/worker/test_worker_advance_worker_advance_repayment.py` — regression tests
- `apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py` — regression tests
- `apps/app_operation/tests/views/` — optional view-level regression tests

## Implementation notes (completed)

- Implemented the net approach: `amount_repayed` now returns
  `to_source - from_source`, where `from_source` sums repayment-type money flowing
  out of `payment_source_fund` (i.e. the mirror reversals of reversed repayments).
  This mirrors `amount_settled` and is safe because legitimate repayments always
  flow `payment_target_fund -> payment_source_fund`, so `from_source` only ever
  contains reversal mirrors.
- Added 3 model-level regression tests per repayable proxy (worker advance, loan):
  full repayment reversed restores remaining balance, partial repayment reversed
  restores remaining balance, and only the reversed repayment is netted out when
  multiple repayments exist.
- Added 2 view-level regression tests:
  - Detail view: after reversing a full repayment, the "Record Repayment" action
    is shown again (i.e. `is_fully_repayed` is False).
  - List view: after reversing a full repayment, the loan entry is `kind == "repayed"`,
    `fully_settled` is False, `paid` is 0 and `remaining` is back to the full amount.
- Verification:
  - `python manage.py check` — no issues.
  - Targeted `manage.py test --parallel=8` on the four touched test modules — 44 tests, OK.
  - Full `manage.py test --parallel=8 apps.app_operation apps.app_transaction` — 1006 tests, OK.
- Note: `pytest` is not usable here (pytest-django is not installed); the project
  relies on Django's built-in test runner (`manage.py test`), matching the
  `testinparallel` rule.

## Follow-up: repayment reversal mirror leaks onto the project's payables page

### Reported symptom
After reversing a worker-advance repayment, the mirror (reversal) transaction
appears on the **project's payables** page as a "Settle" (decrease) row and
drives the payables figure negative.

### Is it correct? No.
For the project that advanced money to a worker, the worker advance is a
**receivable**, not a payable:
- Advance payment `A` (project -> worker, WORKER_ADVANCE_PAYMENT) is counted as
  an increase of the project's receivables.
- Original repayment `R` (worker -> project, WORKER_ADVANCE_REPAYMENT) decreases
  that receivable.
- Reversal mirror `R'` (project -> worker, WORKER_ADVANCE_REPAYMENT): the original
  `R` is correctly excluded once reversed (via the `reversed_by` filter), so the
  receivable correctly returns to the full advance. BUT `R'` has the project as
  its **source** and matches `decrease_as_source` (WORKER_ADVANCE_REPAYMENT is in
  the payables decrease bucket), so it is wrongly counted as a payables decrease.

The same classification error exists in both the model and the view:
- [`Entity.payables_at`](apps/app_entity/models/__init__.py:469) via
  [`_tx_sum_excluding_reversed`](apps/app_entity/models/__init__.py:447) (excludes
  reversed originals but **includes** reversal mirrors), so the project's
  `payables` value itself is wrong (negative).
- [`_build_obligation_transactions`](apps/app_transaction/views.py:117) (the
  payables/receivables pages), which likewise only excludes reversed originals
  (line 149-151) and lets `R'` appear as a spurious row.

### Root cause
Reversal mirror transactions (`reversal_of__isnull=False`) are included in the
payables/receivables bucket sums. Because `reverse()` swaps source/target, the
mirror lands in a source/target bucket intended for the *opposite* party (the
debtor repaying). The type+role matching cannot tell a genuine repayment by the
debtor from a reversal mirror created for the creditor.

### Fix
Exclude reversal transactions (`reversal_of__isnull=True`) from payables/receivables,
consistent with how reversed originals are already excluded and how active
transactions are identified elsewhere (e.g. `_requires_transaction_reversal`):
1. [`_tx_sum_excluding_reversed`](apps/app_entity/models/__init__.py:447) — add
   `reversal_of__isnull=True` to the filter (fixes `payables_at`/`receivables_at`
   and the entity detail summary).
2. [`_build_obligation_transactions`](apps/app_transaction/views.py:117) — add
   `reversal_of__isnull=True` to the query filter (removes the spurious row from
   the payables/receivables pages).

This is safe: reversal mirrors are not independent obligations; the original is
already excluded once reversed, so excluding the mirror cannot double-count or
under-count. `balance_at`/`profit_loss` are intentionally left unchanged (they
rely on including reversals with negation for period correctness).

### Audit-trail consideration (why users can still see reversals)
Excluding reversal mirrors from the payables/receivables pages does NOT remove
visibility of reversed transactions. They remain visible, with `REVERSED` /
`REVERSAL` badges and links, on:
- The **operation detail** page's repayment table
  ([`invoice_repayment_summary.html`](apps/app_operation/templates/app_operation/snippets/detail/invoice_repayment_summary.html:39)),
  rendered for repayable operations via
  [`financial_summary.html`](apps/app_operation/templates/app_operation/snippets/detail/financial_summary.html:25).
- The **entity payment transactions / balance** page
  ([`entity_payment_transactions.html`](apps/app_transaction/templates/app_transaction/entity_payment_transactions.html:132)),
  which lists every payment-type transaction (both reversed originals and
  reversal mirrors) with a status badge and a link to each transaction detail.
- The **transaction detail** page, which links an original to its reversal.

The payables/receivables pages are obligation *summaries*; the reversal mirror
is not an obligation, so it belongs only in the transaction/audit views, not in
the obligation balance.

### Tests
- Entity model: give a worker advance, repay in full, reverse the repayment ->
  assert the project's `payables` is `0` (not negative) and its `receivables`
  equals the advance amount; assert the worker's payables return to the full
  advance (still owed).
- Payables view: after the same scenario, the project's payables page has no
  transactions (no repayment-reversal row) and `current_obligation` is `0`.

### Verification
- `python manage.py check`
- `manage.py test --parallel=8 apps.app_entity apps.app_transaction`

## Implementation notes (follow-up completed)

- Model: [`Entity._tx_sum_excluding_reversed`](apps/app_entity/models/__init__.py:447) now
  also filters `reversal_of__isnull=True`, so `payables_at()`/`receivables_at()` (and the
  entity detail summary) ignore reversal mirrors. `balance_at()`/`profit_loss()` are
  unchanged (they intentionally include reversals with negation).
- View: [`_build_obligation_transactions`](apps/app_transaction/views.py:117) now also
  filters `reversal_of__isnull=True`, so the payables/receivables pages no longer show the
  spurious reversal-mirror row and `current_obligation` matches the model.
- Added `EntityObligationRepaymentReversalTests` in
  [`apps/app_transaction/tests.py`](apps/app_transaction/tests.py): after a full
  worker-advance repayment is reversed, the project's `payables` stay `0` (not negative),
  its `receivables` stay at the advance amount, the worker's `payables` return to the full
  advance, the project's payables page is empty, and its receivables page shows only the
  advance.
- Audit trail preserved: reversed/reversal transactions remain visible with badges on the
  operation detail page, the entity payment-transactions (balance) page, and the
  transaction detail page.
- Verification:
  - `python manage.py check` — no issues.
  - `manage.py test --parallel=8 apps.app_transaction apps.app_entity` — 148 tests, OK.
  - Full `manage.py test --parallel=8` — 1320 tests, OK.
