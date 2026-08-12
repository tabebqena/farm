# Fix: Loan repayment allowed with no disbursement / repayment exceeding disbursed sum

## Problem statement

A loan that has **no** `LOAN_PAYMENT` (disbursement) transaction can still have
`LOAN_REPAYMENT` transactions recorded, and repayments can exceed the amount
actually disbursed. This drives the debtor's payables / creditor's receivables
negative and violates the business rule that repayments are a recovery of what
was actually lent out.

## Root cause

[`LinkedRePaymentTransactionMixin.validate_repayement_amount()`](apps/app_base/mixins.py:511)
in `apps/app_base/mixins.py` validates a repayment amount only against:

```python
amount_remaining_to_repay = total_repayable_amount - amount_repayed
```

where `total_repayable_amount` is the **full operation amount** (e.g. a 1000
loan). It never compares against the net disbursed amount. For loans
(`_is_one_shot_operation=False`, `can_pay=False`, optional multiple
disbursements), a loan can exist with zero `LOAN_PAYMENT` yet still accept
repayments up to the full loan amount.

This buggy behavior is explicitly asserted in
[`test_loan_loan_repayment.py`](apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py:205)
(`test_repayment_without_disbursement_drives_obligations_negative`).

## Requirement

The sum of **active** (non-reversed, non-reversal) repayment transactions must
never exceed the payment (disbursement) transaction sum:

```
sum(active LOAN_REPAYMENT)  <=  sum(LOAN_PAYMENT)
```

In mixin terms (both are net-of-reversal):
`amount_repayed <= amount_settled`.

## Design decision (confirmed)

Cap the repayable amount by the net disbursed amount. This keeps the UI
(`amount_remaining_to_repay`, `is_fully_repayed`) consistent with the rule:

- `repayable_amount = min(total_repayable_amount, amount_settled)`
- `amount_remaining_to_repay = repayable_amount - amount_repayed`
- an undisbursed loan shows `0` remaining and rejects any repayment
- `is_fully_repayed` is reached once all disbursed money is recovered

Worker advance is unaffected: it is one-shot, its `WORKER_ADVANCE_PAYMENT` is
created at save and equals the advance amount, so `min(amount, amount_settled)`
equals the advance amount (no behavioural change).

## Files to change

### 1. `apps/app_base/mixins.py` — `LinkedRePaymentTransactionMixin`

Add a `repayable_amount` property and switch the dependent properties to it:

```python
@property
def repayable_amount(self):
    """Maximum total repayable: the lesser of the operation total and the
    net amount actually disbursed (payment transaction sum)."""
    if hasattr(self, "amount_settled"):
        return min(self.total_repayable_amount, self.amount_settled)
    return self.total_repayable_amount

@property
def amount_remaining_to_repay(self):
    return self.repayable_amount - self.amount_repayed

@property
def is_fully_repayed(self) -> bool:
    return self.amount_repayed >= self.repayable_amount

@property
def is_overpaid_repayed(self) -> bool:
    return self.amount_repayed > self.repayable_amount
```

`validate_repayement_amount()` is left unchanged — it already reads
`amount_remaining_to_repay`, which now automatically enforces the cap. The
`hasattr(self, "amount_settled")` guard keeps the mixin safe if ever used
without `LinkedPaymentTransactionMixin`.

### 2. `apps/app_operation/views/detail.py` — over-repayment display

Update the `over_repayment_amount` computation (around line 125) to use
`repayable_amount` instead of `total_repayable_amount` so the displayed
over-repayment matches the capped `is_overpaid_repayed`:

```python
over_repayment_amount = float(
    operation.amount_repayed - operation.repayable_amount
    if operation.is_overpaid_repayed
    else Decimal("0.00")
)
```

### 3. `apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py`

- In `setUp`, disburse the full loan amount after saving the loan:
  `self.op.create_payment_transaction(amount=Decimal("1000.00"), officer=self.officer_user, date=date.today())`.
- `test_repayment_decreases_debtor_payables` /
  `test_repayment_decreases_creditor_receivables`: drop their own 500
  disbursement (setUp now disburses 1000) and expect `800.00` (1000 − 200).
- Replace `test_repayment_without_disbursement_drives_obligations_negative`
  with a test that creates a fresh **undisbursed** loan and asserts
  `create_repayment_transaction` raises `ValidationError` (and that
  payables/receivables stay 0).
- Add regression tests:
  - repayment blocked when no disbursement exists (covered above).
  - repayment cannot exceed total disbursed: loan 1000, disburse 400, repay
    400 OK, a further repayment raises; `amount_remaining_to_repay` is 0.
  - `amount_remaining_to_repay` equals the disbursed amount minus repaid.

### 4. `apps/app_operation/tests/operations/loan/test_loan_loan_create.py`

- Update `test_amount_remaining_to_repay_equals_issuance_amount_initially`
  (line 107): an undisbursed loan now has `amount_remaining_to_repay == 0`.
  Rename to reflect the new semantics (e.g.
  `test_amount_remaining_to_repay_is_zero_without_disbursement`).

### 5. `apps/app_operation/tests/views/test_views_get_operation_list_view.py`

- `test_operation_list_not_fully_repayed_after_repayment_reversed` (line 111):
  disburse the full 1000 before recording the repayment
  (`loan.create_payment_transaction(amount=Decimal("1000.00"), ...)`) so the
  repayment is valid; the final `remaining == 1000` assertion still holds.

### 6. `apps/app_operation/tests/views/test_views_get_operation_detail_view.py`

- `_make_repayable_loan` (line 199): disburse the full 1000 right after
  creating the loan so the three repayment-based tests stay valid.

### 7. `apps/app_operation/tests/views/test_views_post_repayment_recording_view.py`

- `setUp`: inject funds into the lender (so the disbursement balance check
  passes) and disburse the full 2000 after creating the loan, so the POST
  repayment tests are valid. `test_invalid_form_amount_exceeds_balance`
  (3000 > 2000 remaining) still gets an amount error.

### 8. `apps/app_operation/tests/base.py` — test matrix

- Update `("LOAN", "create", "SE8")` to the renamed create test.
- Update `("LOAN", "repay", "SE4+no_disbursement_negative")` to point at the
  new "blocked without disbursement" test.

### 9. `specs/operations/op_8_loan.md`

- Update the `repay` validation notes: remaining to repay is capped by the
  disbursed amount; repayment is blocked when no disbursement exists.
- Update the `amount_remaining_to_repay` task line
  (`issuance_amount - sum(repayments)`) to reflect the disbursement cap.
- Mark the new verification tasks for the blocked-without-disbursement and
  capped-by-disbursement rules.

## Verification

- `python manage.py check`
- Targeted tests:
  - `python manage.py test --parallel=8 apps.app_operation.tests.operations.loan.test_loan_loan_repayment`
  - `python manage.py test --parallel=8 apps.app_operation.tests.operations.loan.test_loan_loan_create`
  - `python manage.py test --parallel=8 apps.app_operation.tests.views.test_views_get_operation_list_view`
  - `python manage.py test --parallel=8 apps.app_operation.tests.views.test_views_get_operation_detail_view`
  - `python manage.py test --parallel=8 apps.app_operation.tests.views.test_views_post_repayment_recording_view`
  - `python manage.py test --parallel=8 apps.app_operation.tests.operations.worker.test_worker_advance_worker_advance_repayment`
- Broader: `python manage.py test --parallel=8 apps.app_operation apps.app_transaction apps.app_base`

## Notes / edge cases

- Pre-existing over-repaid data (repayment > disbursement) is not retroactively
  corrected; the fix only prevents new violations and makes the derived amounts
  reflect the cap.
- `is_overpaid_repayed` / `detail.py` use `repayable_amount`, so legacy
  over-repaid rows surface consistently in the detail view.

## Implementation notes (completed)

- `apps/app_base/mixins.py`: added `LinkedRePaymentTransactionMixin.repayable_amount`
  = `min(total_repayable_amount, amount_settled)` (falling back to
  `total_repayable_amount` when `amount_settled` is unavailable) and routed
  `amount_remaining_to_repay`, `is_fully_repayed`, `is_overpaid_repayed`
  through it. `validate_repayement_amount()` is unchanged — it now reads the
  capped remaining automatically, so an undisbursed loan has
  `amount_remaining_to_repay == 0` and any repayment raises.
- `apps/app_operation/views/detail.py`: `over_repayment_amount` now uses
  `repayable_amount` instead of `total_repayable_amount`.
- `apps/app_operation/tests/operations/loan/test_loan_loan_repayment.py`:
  disburse the full loan in `setUp`, added `_make_loan` helper, adjusted the
  two payables/receivables tests to expect 800, replaced
  `test_repayment_without_disbursement_drives_obligations_negative` with
  `test_repayment_blocked_when_no_disbursement`, and added
  `test_amount_remaining_to_repay_reflects_disbursed_cap` and
  `test_repayment_cannot_exceed_total_disbursed`.
- `apps/app_operation/tests/operations/loan/test_loan_loan_create.py`:
  `test_amount_remaining_to_repay_equals_issuance_amount_initially` renamed to
  `test_amount_remaining_to_repay_is_zero_without_disbursement` (undisbursed
  loan → remaining 0).
- `apps/app_operation/tests/operations/loan/test_loan_loan_reversal.py`:
  `test_reversal_blocked_when_repayment_exists` now disburses first;
  `test_reversal_allowed_when_repayment_is_reversed` was impossible under the
  new rule (a repayment requires a disbursement, and any LOAN_PAYMENT blocks
  loan reversal) so it became `test_reversal_still_blocked_after_repayment_reversed`.
- `apps/app_operation/tests/views/test_views_get_operation_list_view.py` and
  `.../test_views_get_operation_detail_view.py`: seed a 1000 disbursement
  before recording loan repayments.
- `apps/app_operation/tests/views/test_views_post_repayment_recording_view.py`:
  inject lender funds and disburse the full 2000 in `setUp`.
- `apps/app_operation/tests/base.py`: updated the `("LOAN", "create", "SE8")`
  and `("LOAN", "repay", "SE4+no_disbursement_*")` manifest mappings to the
  renamed/replaced tests.
- `specs/operations/op_8_loan.md`: documented the disbursement cap, that an
  undisbursed loan is not repayable, and updated the task checklist.
- Verification: `python manage.py check` OK; targeted suites OK; full project
  `manage.py test --parallel=8` — 1415 tests, OK.
