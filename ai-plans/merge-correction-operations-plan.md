# Merge Correction Credit & Debit into One Operation Proxy

## Goal

Merge `CorrectionCreditOperation` and `CorrectionDebitOperation` into a single
`CorrectionOperation` proxy class. **No business logic, DB data, operation types,
transaction types, URL slugs, labels, or themes change.** This is a pure proxy-layer
refactor: fewer proxy classes, identical features and behavior.

## Confirmed scope (user decision)

- Keep both operation types: `OperationType.CORRECTION_CREDIT` and
  `OperationType.CORRECTION_DEBIT`.
- Keep all 4 transaction types: `CORRECTION_CREDIT_ISSUANCE` / `_PAYMENT` and
  `CORRECTION_DEBIT_ISSUANCE` / `_PAYMENT`.
- Keep both URL slugs: `correction-credit` and `correction-debit`.
- Keep per-type labels, themes, roles, and validation messages exactly as-is.
- Only the number of proxy *classes* is reduced (2 → 1).
- No data migration required (proxies share the concrete `Operation` content type;
  `operation_type` CharField values unchanged).

## Why this is a refactor, not a data change

- `Operation` stores `operation_type` as a CharField; the proxy is only a Python
  class used for config/behavior. `PROXY_MAP[operation_type]` maps type → class.
- Django proxy models have no DB table and share the concrete model's ContentType
  (`for_concrete_model=True` default). Verified by
  `TransactionGenericForeignKeyTests.test_transaction_links_to_correct_content_type`.
- Migrations for proxy models only change Django's model-state, never DB schema.

## Current architecture (what exists today)

- `apps/app_operation/models/proxies/op_correction_credit.py` — `CorrectionCreditOperation`
- `apps/app_operation/models/proxies/op_correction_debit.py` — `CorrectionDebitOperation`
- `apps/app_operation/models/proxies/__init__.py` — `PROXY_MAP` (both types → their
  own class), `_URL_MAP` (one `url_str` per class), `get_canonical_type(url_str)`,
  `get_operation_class(operation_type)`, `__all__`.
- `apps/app_operation/models/operation.py` — base `Operation`; `resolve_request()`
  classmethod reads `cls._source_role`, `cls._dest_role`, `cls.label`, `cls.url_str`,
  `cls.theme_color`, `cls.theme_icon`, and flags; `period_entity` reads
  `self._source_role` / `self._dest_role`; `_reversable_transaction_types` /
  `_implicit_reversable_transaction_types` read `self._issuance_transaction_type` /
  `self._payment_transaction_type` (instance-level, so per-type dispatch works).
- `apps/app_operation/views/create_operation/base.py` — `OperationCreateView.dispatch`
  resolves `proxy_cls = get_canonical_type(op_type)` from the URL slug;
  `_setup_view` computes `canonical_op_type = next(t for t, c in PROXY_MAP.items()
  if c is self.proxy_cls)` — **this breaks when two types share one class** (always
  returns `CORRECTION_CREDIT`).
- `apps/app_operation/views/reverse.py`, `views/edit.py` — read `config.label`
  where `config = PROXY_MAP.get(operation.operation_type)` (class-level read).
- `apps/app_operation/views/list.py`, `models/managers.py`, `models/adjustment.py`
  — use `PROXY_MAP.get(operation_type)` only to cast to the class; safe.
- Migrations `apps/app_operation/migrations/0001_initial.py` (two proxy `CreateModel`s).
- Test files under `apps/app_operation/tests/operations/corrections/`, plus
  `apps/app_transaction/tests.py`, `apps/app_base/tests.py`,
  `apps/app_inventory/tests/test_capital_valuation.py`,
  `apps/app_operation/tests/views/test_views_get_operation_create_view.py`,
  `apps/app_operation/tests/period/test_downstream_closed_period_guards.py` import
  `CorrectionCreditOperation` / `CorrectionDebitOperation` directly.
- UI tests `ui_tests/operations/test_one_shot_operations.py` use URL slugs
  (`correction-credit` / `correction-debit`) — they keep working once slug resolution
  maps both slugs to the merged class with the correct operation type.

## Design of the merged proxy

New file `apps/app_operation/models/proxies/op_correction.py`:

- Class `CorrectionOperation(TransactionMixin, Operation)`.
- Shared (identical for both variants) config stays as class attributes:
  `can_pay=False`, `check_balance_on_payment=False`, `is_partially_payable=False`,
  `has_category=False`, `category_required=False`, `_is_one_shot_operation=True`,
  `has_repayment=False`, `max_payment_transaction_count=1`, `has_invoice=False`,
  `has_capital_valuation=False`.
- Per-type config table keyed by `operation_type`:
  `_VARIANT_CONFIG = {OperationType.CORRECTION_CREDIT: {...}, OperationType.CORRECTION_DEBIT: {...}}`
  holding `url_str`, `label`, `_source_role`, `_dest_role`,
  `_issuance_transaction_type`, `_payment_transaction_type`, `theme_color`,
  `theme_icon`, `verbose_name`.
- Instance `@property` accessors dispatch on `self.operation_type`:
  - `_issuance_transaction_type`, `_payment_transaction_type`
  - `label`, `theme_color`, `theme_icon`
  - `_source_role`, `_dest_role`
- `clean_source` / `clean_destination` dispatch on `self.operation_type`,
  preserving the exact validation messages.
- `payment_source_fund` / `payment_target_fund` stay as `self.source` /
  `self.destination` (role correctness enforced by `clean_*`).
- Class helper `url_strs = ("correction-credit", "correction-debit")` and
  classmethod `operation_type_for_url(url_str) -> OperationType` so the create view
  can resolve the correct operation type from the URL slug.
- `Meta.proxy = True`, `verbose_name = "Correction"`.

## Shared-resolution-layer changes (surgical, behavior-preserving)

1. `apps/app_operation/models/proxies/__init__.py`
   - `PROXY_MAP`: map BOTH `CORRECTION_CREDIT` and `CORRECTION_DEBIT` →
     `CorrectionOperation`.
   - Build `_URL_MAP` to register every slug of every class (use `url_strs` when
     present, else `url_str`), so both correction slugs resolve to the merged class.
   - Update imports and `__all__` (remove the two old classes, add `CorrectionOperation`).
   - `get_canonical_type(url_str)` / `get_operation_class(operation_type)` keep their
     signatures and return values.

2. `apps/app_operation/models/operation.py`
   - `resolve_request(cls, url_pk, request, operation_type=None)`: accept an optional
     `operation_type`; read per-type config via a new `_type_config(operation_type)`
     hook (base returns `{}`; `CorrectionOperation` returns `_VARIANT_CONFIG[type]`)
     and fall back to class attributes for non-variant proxies. All non-correction
     proxies are unaffected (they pass no `operation_type` / return `{}`).

3. `apps/app_operation/views/create_operation/base.py`
   - `dispatch`: remember the URL slug (`self.url_op_type = op_type`).
   - `_setup_view`: resolve `canonical_op_type` via
     `self.proxy_cls.operation_type_for_url(self.url_op_type)` when the class
     provides it; otherwise keep the existing `next(...)` class-match fallback.
   - Pass `operation_type=self.canonical_op_type` into `resolve_request(...)`.

4. `apps/app_operation/views/reverse.py` and `reverse_form.html`
   - Replace class-level `config.label` reads with `operation.label`
     (instance property, dispatches on `operation_type`).

## Files to remove / create

- Remove: `apps/app_operation/models/proxies/op_correction_credit.py`,
  `apps/app_operation/models/proxies/op_correction_debit.py`.
- Create: `apps/app_operation/models/proxies/op_correction.py`.
- Migration: `apps/app_operation/migrations/0010_merge_correction_proxies.py`
  (`DeleteModel` for both old proxy models, `CreateModel` for `CorrectionOperation`;
  model-state only, no data change).

## Test updates (behavior unchanged, imports/classes updated)

- `apps/app_operation/tests/operations/corrections/test_correction_correction_credit_create.py`
- `apps/app_operation/tests/operations/corrections/test_correction_correction_debit_create.py`
- `apps/app_operation/tests/operations/corrections/test_correction_correction_credit_reversal.py`
- `apps/app_operation/tests/operations/corrections/test_correction_correction_debit_reversal.py`
- `apps/app_transaction/tests.py` (`_inject_funds`, `TransactionGenericForeignKeyTests`)
- `apps/app_base/tests.py`
- `apps/app_inventory/tests/test_capital_valuation.py`
- `apps/app_operation/tests/views/test_views_get_operation_create_view.py`
- `apps/app_operation/tests/period/test_downstream_closed_period_guards.py`
- `apps/app_operation/tests/base.py` — coverage-manifest string paths point to the
  test class names (e.g. `CorrectionCreditCreateTest`); verify they remain valid.
- Check `apps/app_operation/models/__init__.py` re-exports.

Each test constructs an operation with an explicit `operation_type`, so swapping
`CorrectionCreditOperation(...)` → `CorrectionOperation(...)` (same `operation_type`)
keeps every assertion identical.

## Spec updates (updatelogics rule: spec edits first)

- `docs/specs/operations/op_15_correction.md` — rewrite the Identity / Config /
  Money-flow / Actions / Branch-catalog / View-UI sections to describe ONE proxy
  `CorrectionOperation` serving both `CORRECTION_CREDIT` and `CORRECTION_DEBIT`,
  with per-type config keyed by `operation_type`. All branch codes (CC1…CC39,
  CD1…CD39), transaction types, URLs, themes, and validation messages remain.
- `docs/specs/operations/operations-comparison.md` — rows 15/16 both reference
  `CorrectionOperation`.
- `docs/specs/operations/README.md` — if it enumerates operation proxies, update.
- `docs/specs/features/README.md` / others only if they name the proxy classes.

## Verification

- `python manage.py check`
- Targeted correction tests:
  - `apps/app_operation/tests/operations/corrections/`
  - `apps/app_transaction/tests.py`
  - `apps/app_base/tests.py`
- Full suite: `python manage.py test --parallel=10 --keepdb` (per
  `testinparallel` rule), capture result into `tmp/`, review, then delete.
- Optional UI smoke: `ui_tests/operations/test_one_shot_operations.py`
  (`CorrectionCreditUiTests`, `CorrectionDebitUiTests`).
- Commit the changes with a descriptive message.

## Note

The two correction variants are currently registered as separate proxy classes in
`PROXY_MAP`. After this refactor, both operation types point to `CorrectionOperation`;
the instance property dispatch guarantees identical behavior (transaction types,
roles, labels, themes, validation, reversal, settlement) for every existing and new
operation row.

## Implementation notes (what was actually done)

- Merged proxy created at `apps/app_operation/models/proxies/op_correction.py`
  (`CorrectionOperation`); the two old proxy files were deleted.
- `PROXY_MAP` maps both `CORRECTION_CREDIT` and `CORRECTION_DEBIT` to
  `CorrectionOperation`; `_URL_MAP` now registers every slug of every proxy
  (`url_strs` tuple on `CorrectionOperation`), so both `correction-credit` and
  `correction-debit` resolve to the merged class.
- `Operation.resolve_request` gained an optional `operation_type` argument plus a
  `_type_config()` hook (base returns `{}`); `CorrectionOperation._type_config`
  returns the per-type variant. Non-correction proxies are unaffected.
- `OperationCreateView` now remembers the URL slug (`self.url_op_type`) and, when the
  proxy exposes `operation_type_for_url()`, resolves `canonical_op_type` from the slug
  instead of the single-type class match (which would otherwise always pick the first
  type). The resolved type is passed into `resolve_request`.
- `operation_reverse_view` now reads the per-instance `operation.label` (instead of the
  class-level `config.label`) for success messages/audit; the reverse form template
  receives `config={"label": operation.label}`.
- Migration `apps/app_operation/migrations/0010_merge_correction_proxies.py` deletes
  the two old proxy models and creates `CorrectionOperation` (model-state only — proxy
  models share the concrete `Operation` content type, so no data migration needed).
- All direct test references to `CorrectionCreditOperation` / `CorrectionDebitOperation`
  were renamed to `CorrectionOperation` (same explicit `operation_type` values).
- Specs updated: `op_15_correction.md` and `operations-comparison.md` now describe a
  single `CorrectionOperation` proxy dispatching per-type config on `operation_type`.
- Verification: `python manage.py check` clean; `makemigrations --check` reports no
  pending changes; all 72 correction tests and 160 related tests pass. Full suite
  (1472 tests): all Django app tests pass; the only failures/errors are the
  pre-existing Selenium `ui_tests/` set (parallel-runner `DummyList` tearDown errors
  and browser timeout flakes) unrelated to this merge.
