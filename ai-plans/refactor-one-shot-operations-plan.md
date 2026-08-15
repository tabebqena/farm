# Refactor One-Shot Operations & Transaction Mixins

## Goal

Improve the **readability, abstraction, and usability** of the one-shot operation
machinery by editing the transaction mixins (`apps/app_base/mixins.py`) and the
`Operation` base model (`apps/app_operation/models/operation.py`) plus the affected
proxy classes. **No business logic, DB data, operation types, transaction types, URL
slugs, labels, themes, or validation messages change.** This is a pure internal refactor.

## Confirmed behavior (from specs — NOT a behavior change)

The one-shot contract is intended and documented in
[`docs/specs/operations/operations-comparison.md`](../docs/specs/operations/operations-comparison.md):

- One-shot operations (Cash Injection, Cash Withdrawal, Project Funding, Project Refund,
  Internal Transfer, Correction Credit/Debit, Worker Advance, and the inventory
  Birth/Death/Consumption) settle in full at creation: the **pay** action is `E@create`
  — issuance + a single payment fire atomically at `save()`, with no standalone
  post-create pay action.
- `_is_one_shot_operation = True` + `max_payment_transaction_count = 1` enforce the
  "exactly one payment, amount must equal the operation amount" rule
  (see `create_payment_transaction` guard and the `test_one_shot_prevents_second_payment`
  test family).
- Worker Advance is a special one-shot: it keeps `_is_one_shot_operation = True` and
  `max_payment_transaction_count = 1` but is **repayable** (`has_repayment = True`).

Because behavior is preserved, **no spec edits are required** — the specs already
describe exactly what the code does today.

## Current duplication / pain points

### 1. Repeated config block in every one-shot proxy

Seven proxy classes repeat the same ~7 config lines:

```python
can_pay = False
is_partially_payable = False
has_category = False
category_required = False
_is_one_shot_operation = True
has_repayment = False
max_payment_transaction_count = 1
```

Affected: `op_cash_injection.py`, `op_cash_withdrawal.py`, `op_project_funding.py`,
`op_project_refund.py`, `op_internal_transfer.py`, `op_correction.py`,
`op_worker_advance.py` (the last overrides `has_repayment = True`).

Note that several of these are already the `Operation` base defaults
(`can_pay`, `is_partially_payable`, `has_category`, `category_required`,
`has_repayment` are all `False` on `Operation`), so they are doubly redundant.

### 2. Confusing flag comment block

`LinkedPaymentTransactionMixin` lines ~245–262 carry a tangled comment block
("Flags:", "End of flags", "# ################################################")
that is hard to read and mixes unrelated concerns.

### 3. Duplicated `save()` plumbing

Both `LinkedIssuanceTransactionMixin.save()` and `LinkedPaymentTransactionMixin.save()`
repeat the identical reversal-skip branch:

```python
if getattr(self, "reversal_of", None) is not None and self.reversal_of:
    ...  # Don't create transactions
elif getattr(self, "reversed_by", None) is not None and self.reversed_by:
    ...  # Don't create transactions
else:
    ...  # schedule the tx task
```

### 4. Scattered one-shot knowledge

`_is_one_shot_operation` is consulted in several places (mixin `create_payment_transaction`,
mixin `save`, `Operation._implicit_reversable_transaction_types`, and the detail/list
views). There is no single, readable public entry point (views reach into the private
`_is_one_shot_operation` attribute directly).

## Proposed design

### A. New `OneShotTransactionMixin` in `apps/app_base/mixins.py`

```python
class OneShotTransactionMixin(TransactionMixin):
    """Operations settled in full at creation.

    A one-shot operation writes an issuance transaction plus exactly one payment
    transaction atomically at save() (pay = E@create per the operation specs).
    Config: no standalone pay action, single payment, amount must equal the
    operation amount.
    """
    _is_one_shot_operation = True
    max_payment_transaction_count = 1
    can_pay = False
    is_partially_payable = False
```

Placement: after `TransactionMixin` (so the new mixin stack order stays
`OneShotTransactionMixin -> TransactionMixin -> LinkedIssuance/… -> LinkedPayment/…`).

### B. Shared save() plumbing to remove the duplicated reversal-skip

Introduce a small base used by the transaction-creating mixins:

```python
class AutoTransactionMixin(BaseModelMixin):
    """Shared save() plumbing for mixins that auto-create transactions at save time.

    Subclasses implement ``_schedule_transaction_tasks(kwargs)`` to append their
    post_save_tasks. Reversal records (reversal_of / reversed_by) never create
    transactions.
    """

    def _is_reversal_record(self) -> bool:
        return bool(getattr(self, "reversal_of", None)) or bool(
            getattr(self, "reversed_by", None)
        )

    def _schedule_transaction_tasks(self, kwargs: dict) -> None:
        raise NotImplementedError

    def save(self, *args, **kwargs) -> None:
        with db_transaction.atomic():
            if self.pk is None and not self._is_reversal_record():
                self._schedule_transaction_tasks(kwargs)
            return super().save(*args, **kwargs)
```

`LinkedIssuanceTransactionMixin` and `LinkedPaymentTransactionMixin` inherit it and
implement `_schedule_transaction_tasks` (issuance task / one-shot payment task
respectively), preserving the existing `post_save_tasks` mechanism exactly.

### C. Clean up the flag comment block in `LinkedPaymentTransactionMixin`

Replace the noisy "Flags: … End of flags" comment with a concise docstring describing
the three configuration knobs (`_payment_transaction_type`,
`max_payment_transaction_count`, `check_balance_on_payment`) and the one-shot flag.

### D. Public usability helper on `Operation`

Add a public, documented property so callers/views stop reaching into the private
attribute:

```python
@property
def is_one_shot(self) -> bool:
    """Whether this operation settles in full at creation (one-shot)."""
    return self._is_one_shot_operation
```

The detail view (`views/detail.py`) may optionally switch to `operation.is_one_shot`.

### E. Update the one-shot proxies

Each simple one-shot proxy becomes:

```python
class CashInjectionOperation(OneShotTransactionMixin, Operation):
    _issuance_transaction_type = TransactionType.CASH_INJECTION_ISSUANCE
    _payment_transaction_type = TransactionType.CASH_INJECTION_PAYMENT

    url_str = "cash-injection"
    label = "Cash Injection"
    _source_role = "world"
    _dest_role = "url"
    theme_color = "success"
    theme_icon = "bi-box-arrow-in-down"

    # … payment_source_fund / payment_target_fund / clean_source / clean_destination
```

Dropped from each proxy (now inherited): `can_pay`, `is_partially_payable`,
`has_category`, `category_required`, `_is_one_shot_operation`, `has_repayment`,
`max_payment_transaction_count`.

Worker Advance (repayable one-shot) uses `OneShotTransactionMixin` combined with the
repayment mixin:

```python
class WorkerAdvanceOperation(OneShotTransactionMixin, LinkedRePaymentTransactionMixin, Operation):
    has_repayment = True
    is_repayable = True
    repayment_label = "Advance Repayment"
    …
```

(`has_repayment`/`is_repayable`/`repayment_label` are explicit because they are the
non-default part of Worker Advance; the one-shot flags come from the mixin.)

## Files to edit

1. `apps/app_base/mixins.py` — add `OneShotTransactionMixin`, `AutoTransactionMixin`;
   refactor the two `save()` methods; clean the flag comment.
2. `apps/app_operation/models/operation.py` — add `is_one_shot` public property.
3. `apps/app_operation/models/proxies/op_cash_injection.py` — use `OneShotTransactionMixin`, drop redundant config.
4. `apps/app_operation/models/proxies/op_cash_withdrawal.py` — same.
5. `apps/app_operation/models/proxies/op_project_funding.py` — same.
6. `apps/app_operation/models/proxies/op_project_refund.py` — same.
7. `apps/app_operation/models/proxies/op_internal_transfer.py` — same.
8. `apps/app_operation/models/proxies/op_correction.py` — same.
9. `apps/app_operation/models/proxies/op_worker_advance.py` — use `OneShotTransactionMixin` + repayment mixin.
10. `apps/app_operation/views/detail.py` — optionally use `operation.is_one_shot`.

## Tests

- Existing coverage already pins one-shot behavior:
  `tests/operations/*/test_*_{create,reversal}.py`,
  `tests/operations/worker/test_worker_advance_worker_advance_create.py`,
  `tests/test_operation_mixins.py`.
- Add a small structural test to `tests/test_operation_mixins.py` asserting that the
  one-shot proxies expose `_is_one_shot_operation = True`,
  `max_payment_transaction_count = 1`, `can_pay = False`, `is_partially_payable = False`
  (i.e. the mixin default holds) and that `Operation.is_one_shot` reads the flag.
- Run per the testing rules:
  `python3 manage.py test --parallel=10 --keepdb` (capture to `tmp/`, then remove the
  temporary file). No schema change is expected, but run `--keepdb` and fall back to a
  rebuild if a model-state change is detected.

## Out of scope

- No spec edits (behavior preserved).
- No migrations expected (proxies share the concrete `Operation` table; only Python
  mixin/config changes).
- The inventory one-shots (Birth/Death/Consumption/Capital) are **not** accounting
  operations and intentionally keep no transaction mixin — untouched.

---

## Implementation notes (completed 2026-08-15)

- `apps/app_base/mixins.py`
  - Added `AutoTransactionMixin` — shared `save()` plumbing that skips transaction
    creation for reversal records (`_is_reversal_record()`) and exposes a cooperative
    `_schedule_transaction_tasks(kwargs)` hook.
  - `LinkedIssuanceTransactionMixin` and `LinkedPaymentTransactionMixin` now inherit it
    and each implement `_schedule_transaction_tasks` (calling `super()` so composed
    mixins — e.g. `TransactionMixin`'s issuance + payment — each append their task).
    The duplicated `save()` reversal-skip branch is removed.
  - The noisy flag comment block in `LinkedPaymentTransactionMixin` was replaced with a
    concise docstring describing the config knobs.
- `apps/app_operation/models/operation.py`
  - Added `OneShotTransactionMixin(TransactionMixin)` setting `_is_one_shot_operation`,
    `max_payment_transaction_count = 1`, `can_pay = False`, `is_partially_payable = False`.
  - Added public `Operation.is_one_shot` property (readable alias of the flag).
- One-shot proxies — `op_cash_injection`, `op_cash_withdrawal`, `op_project_funding`,
  `op_project_refund`, `op_internal_transfer`, `op_correction`, `op_worker_advance` —
  now inherit `OneShotTransactionMixin`; the repeated ~7-line config block was removed.
  `WorkerAdvanceOperation` composes `OneShotTransactionMixin` +
  `LinkedRePaymentTransactionMixin` to remain a repayable one-shot.
- `apps/app_operation/views/detail.py` now uses `operation.is_one_shot`.
- `apps/app_operation/tests/test_operation_mixins.py` adds `OneShotOperationConfigTest`
  pinning the one-shot defaults and the public `is_one_shot` property.

**No behavior changed.** Verification:
- `manage.py check` — no issues.
- `manage.py makemigrations --check --dry-run` — no changes detected (proxies only).
- Full app unit/integration suite (ui_tests excluded per project rules):
  `manage.py test apps.app_base apps.app_entity apps.app_transaction apps.app_operation
  apps.app_adjustment apps.app_inventory apps.app_animal --parallel=10 --keepdb`
  → **1428 tests OK** in ~56s.
- One-shot operation suites all green: cash 73, worker 64, funding 80,
  transfer+corrections 116, mixins 8.
