# Merge Capital Gain & Capital Loss into One Operation Proxy

## Goal

Merge `CapitalGainOperation` and `CapitalLossOperation` into a single
`CapitalValuationOperation` proxy class. **No business logic, DB data, operation types,
transaction types, URL slugs, labels, or themes change.** This is a pure proxy-layer
refactor: fewer proxy classes, identical features and behavior (mirrors the completed
Correction merge — see [`merge-correction-operations-plan.md`](merge-correction-operations-plan.md)).

## Confirmed scope (user decision — Option B)

- Keep both operation types: `OperationType.CAPITAL_GAIN` and
  `OperationType.CAPITAL_LOSS`.
- Keep both URL slugs: `capital-gain` and `capital-loss`.
- Keep per-type labels ("Capital Gain Issuance" / "Capital Loss Issuance"), roles
  (system→url gain / url→system loss), and validation messages exactly as-is.
- Keep `has_capital_valuation = True`, `can_pay = False`, no settlement, no invoices —
  the value-only stock-event contract from [op_5](../docs/specs/operations/op_5_capital_gain.md)
  and [op_6](../docs/specs/operations/op_6_capital_loss.md).
- Only the number of proxy *classes* is reduced (2 → 1).
- **No data migration**: proxies share the concrete `Operation` table; the
  `operation_type` CharField values are unchanged. A model-state migration
  (DeleteModel ×2 + CreateModel) keeps `makemigrations --check` clean, exactly like
  `0010_merge_correction_proxies.py`.

## Why this is a refactor, not a data change

- `Operation` stores `operation_type` as a CharField; the proxy is only a Python
  class used for config/behavior. `PROXY_MAP[operation_type]` maps type → class.
- Django proxy models have no DB table and share the concrete model's ContentType.
- The inventory layer is already direction-agnostic: `stock.capital_delta()` sums the
  **signed** `ProductCapitalValuation.amount` (positive = gain, negative = loss), so
  both variants flow through the same valuation machinery unchanged.

## Current architecture (what exists today)

- `apps/app_operation/models/proxies/op_capital_gain.py` — `CapitalGainOperation`
  (url_str `capital-gain`, label "Capital Gain Issuance", system→url).
- `apps/app_operation/models/proxies/op_capital_loss.py` — `CapitalLossOperation`
  (url_str `capital-loss`, label "Capital Loss Issuance", url→system).
- `apps/app_operation/models/proxies/__init__.py` — `PROXY_MAP` (both types → their own
  class), `_URL_MAP` (built from `url_strs`/`url_str`), `get_canonical_type`,
  `get_operation_class`, `__all__`.
- `apps/app_operation/models/operation.py` — `Operation`; `resolve_request` already
  accepts `operation_type` and calls `_type_config()`; `_setup_view` in
  `views/create_operation/base.py` already resolves multi-type proxies from the URL slug
  via `operation_type_for_url()` (both hooks were added by the Correction merge).
- `apps/app_operation/views/create_operation/evaluation.py` — `EvaluationCreateView`
  picks `CapitalGainOperation` if `delta > 0` else `CapitalLossOperation`, then calls
  `self._setup_view(...)` (which class-matches PROXY_MAP → first type). After the merge
  this must select the variant explicitly from the delta sign.
- `apps/app_inventory/models.py` — `ProductCapitalValuation.clean()` guards the signed
  amount against `operation.operation_type` (`CAPITAL_GAIN` → positive,
  `CAPITAL_LOSS` → negative) and checks ownership via `operation.inventory_owner_entity`.
- Tests: `apps/app_operation/tests/operations/capital/*`, `apps/app_inventory/tests/`,
  `apps/app_base/tests.py`, `apps/app_adjustment/tests/`,
  `apps/app_operation/tests/operations/{corrections,expense,purchase,sale}/*`,
  `apps/app_operation/tests/period/test_period_model.py`,
  `apps/app_operation/tests/views/*`, and more use `CapitalGainOperation` /
  `CapitalLossOperation` directly (many as a generic "seed project fund" helper).

## Design of the merged proxy

New file `apps/app_operation/models/proxies/op_capital_valuation.py`:

- Class `CapitalValuationOperation(Operation)`.
- Shared (identical for both variants) config stays as class attributes:
  `can_pay=False`, `check_balance_on_payment=False`, `is_partially_payable=False`,
  `has_category=False`, `category_required=False`, `has_repayment=False`,
  `has_invoice=False`, `has_capital_valuation=True`.
- Per-type config table keyed by `operation_type`:
  `_VARIANT_CONFIG = {OperationType.CAPITAL_GAIN: {...}, OperationType.CAPITAL_LOSS: {...}}`
  holding `url_str`, `label`, `_source_role`, `_dest_role`, `verbose_name`.
- Instance `@property` accessors dispatch on `self.operation_type`:
  `label`, `_source_role`, `_dest_role`.
- `clean_source` / `clean_destination` dispatch on `self.operation_type`, preserving
  the exact validation messages from the two former proxies.
- `add_valuation(product, amount, officer=None, notes="")` — identical to the former
  implementations (creates a `ProductCapitalValuation` row; signed amount).
- Class helper `url_strs = ("capital-gain", "capital-loss")` and classmethod
  `operation_type_for_url(url_str) -> OperationType` so `_setup_view` resolves the
  correct operation type from the URL slug.
- `Meta.proxy = True`, `verbose_name = "Capital Valuation"`.

## Shared-resolution-layer changes (surgical, behavior-preserving)

1. `apps/app_operation/models/proxies/__init__.py`
   - `PROXY_MAP`: map BOTH `CAPITAL_GAIN` and `CAPITAL_LOSS` → `CapitalValuationOperation`.
   - `_URL_MAP` already registers every slug via `url_strs` — both slugs resolve to the
     merged class.
   - Update imports and `__all__` (remove the two old classes, add `CapitalValuationOperation`).
   - `get_canonical_type(url_str)` / `get_operation_class(operation_type)` keep their
     signatures and return values.
2. `apps/app_operation/models/__init__.py` — update re-exports.
3. `apps/app_operation/views/create_operation/evaluation.py`
   - Set `self.proxy_cls = CapitalValuationOperation` and choose the variant from the
     delta sign (`self.url_op_type = "capital-gain" if delta > 0 else "capital-loss"`)
     so `_setup_view` resolves `canonical_op_type` correctly; keep the explicit
     `operation_type=...` passed to `create()`.
4. Migration `apps/app_operation/migrations/0011_merge_capital_proxies.py`
   (`DeleteModel` for the two old proxy models, `CreateModel` for
   `CapitalValuationOperation`; model-state only, no data change).

## Files to remove / create

- Remove: `apps/app_operation/models/proxies/op_capital_gain.py`,
  `apps/app_operation/models/proxies/op_capital_loss.py`.
- Create: `apps/app_operation/models/proxies/op_capital_valuation.py`.
- Migration: `apps/app_operation/migrations/0011_merge_capital_proxies.py`.

## Test updates (behavior unchanged, imports/classes updated)

All direct references to `CapitalGainOperation` / `CapitalLossOperation` are renamed to
`CapitalValuationOperation` (same explicit `operation_type` values, so every assertion
is unchanged). Affected test files include (non-exhaustive):

- `apps/app_operation/tests/operations/capital/*`
- `apps/app_operation/tests/operations/{corrections,expense,purchase,sale}/*`
- `apps/app_operation/tests/operations/test_operation_create.py`
- `apps/app_operation/tests/period/test_period_model.py`
- `apps/app_operation/tests/views/*`
- `apps/app_operation/tests/test_operation_mixins.py`
- `apps/app_inventory/tests/test_product.py`, `test_capital_valuation.py`
- `apps/app_base/tests.py`
- `apps/app_entity/tests/test_views_get_entity_detail_view.py`
- `apps/app_adjustment/tests/*`

`apps/app_operation/tests/base.py` coverage-manifest string paths point to test file
names and class names (e.g. `CapitalGainCreateTest`) — those stay valid.

## Spec updates (updatelogics rule: spec edits first)

- `docs/specs/operations/op_5_capital_gain.md` and
  `docs/specs/operations/op_6_capital_loss.md` — update the Identity table "Proxy class"
  row to `CapitalValuationOperation` and note the shared proxy dispatching per-type
  config on `operation_type` (mirror `op_15_correction.md`).
- `docs/specs/operations/operations-comparison.md` — rows 5/6 reference
  `CapitalValuationOperation`.
- `docs/specs/operations/README.md` — only links operation specs; no proxy names to
  change.

## Verification

- `python manage.py check`
- `python manage.py makemigrations --check` (no pending changes)
- Targeted capital tests + related:
  - `apps/app_operation/tests/operations/capital/`
  - `apps/app_inventory/tests/test_capital_valuation.py`
  - `apps/app_inventory/tests/test_product.py`
  - `apps/app_operation/tests/period/test_period_model.py`
- Full suite: `python manage.py test --parallel=10 --keepdb` (per `testinparallel`
  rule), capture result into `tmp/`, review, then delete.
- Commit the changes with a descriptive message.

## Note

After this refactor, both operation types point to `CapitalValuationOperation`; the
instance property dispatch guarantees identical behavior (roles, labels, validation,
reversal, valuation, period assignment) for every existing and new operation row.

## Implementation notes (what was actually done)

- Merged proxy created at `apps/app_operation/models/proxies/op_capital_valuation.py`
  (`CapitalValuationOperation`); the two old proxy files
  (`op_capital_gain.py` / `op_capital_loss.py`) were deleted.
- `PROXY_MAP` maps both `CAPITAL_GAIN` and `CAPITAL_LOSS` to
  `CapitalValuationOperation`; `_URL_MAP` registers every slug of every proxy
  (`url_strs` tuple on `CapitalValuationOperation`), so both `capital-gain` and
  `capital-loss` resolve to the merged class. `models/__init__.py` re-exports were
  updated to the merged class.
- `CapitalValuationOperation` dispatches per-type config (`url_str`, label,
  `_source_role`, `_dest_role`, `verbose_name`) on `operation_type` via
  `_VARIANT_CONFIG`, with instance `@property` accessors for `label` /
  `_source_role` / `_dest_role`, per-type `clean_source` / `clean_destination`
  (preserving the exact validation messages), and the shared
  `add_valuation()` (signed `ProductCapitalValuation.amount`).
- `EvaluationCreateView` now sets `self.proxy_cls = CapitalValuationOperation` and
  resolves the variant from the delta sign via `self.url_op_type` (`capital-gain`
  / `capital-loss`), so `_setup_view` resolves the correct `canonical_op_type`.
- `Operation.inventory_owner_entity` and `ProductCapitalValuation.clean` needed no
  change — both already dispatch on the `operation_type` CharField (kept), so the
  ownership/sign guards behave identically.
- Migration `apps/app_operation/migrations/0011_merge_capital_proxies.py` deletes
  the two old proxy models and creates `CapitalValuationOperation` (model-state
  only — proxy models share the concrete `Operation` content type, so no data
  migration needed).
- All direct test references to `CapitalGainOperation` / `CapitalLossOperation`
  were renamed to `CapitalValuationOperation` (same explicit `operation_type`
  values; duplicated import lines from the mechanical rename were de-duplicated in
  `test_product.py` and `test_operation_mixins.py`).
- Specs updated: `op_5_capital_gain.md`, `op_6_capital_loss.md` and
  `operations-comparison.md` now describe the single `CapitalValuationOperation`
  proxy dispatching per-type config on `operation_type`.
- Verification: `manage.py check` clean; `makemigrations --check` reports no pending
  changes; targeted capital-area tests (141) all pass; full suite (1472 tests) —
  all Django app tests pass, with only the pre-existing Selenium `ui_tests/` set
  failing under the parallel runner (browser timeout flakes / required-field
  harness gaps), unrelated to this merge.
