# Refactor Inventory-Touching Operations & Mixins

## Goal

Improve the **readability, abstraction, and usability** of the operations that touch
inventory — Birth, Death, Consumption, Purchase, Sale, Capital Gain / Capital Loss —
by editing the shared mixins and the `Operation` base model
(`apps/app_operation/models/operation.py`). **No business logic, DB data, operation
types, transaction types, URL slugs, labels, themes, or validation messages change.**
This is a pure internal refactor, plus registration-only spec updates.

## Confirmed behavior (from specs — NOT a behavior change)

The inventory contract is intended and documented:

- **Stock events** (Birth / Death / Consumption) are inventory-only operations with
  **no accounting transactions** — shared config
  `can_pay=False`, `is_partially_payable=False`, `check_balance_on_payment=False`,
  `has_category=False`, `category_required=False`, `has_repayment=False`,
  `has_invoice=True`. See [`docs/specs/features/stock.md`](../docs/specs/features/stock.md)
  §2.3 and the per-op specs [`op_17_birth.md`](../docs/specs/operations/op_17_birth.md),
  [`op_18_death.md`](../docs/specs/operations/op_18_death.md),
  [`op_19_consumption.md`](../docs/specs/operations/op_19_consumption.md) (§1).
- **Capital Gain / Loss** are **value-only** stock writers — `has_invoice=False`,
  `has_capital_valuation=True`; they create a `ProductCapitalValuation` row, never an
  `InvoiceItem` or movement line (see [`stock.md`](../docs/specs/features/stock.md) §4).
- **Purchase / Sale** are accounting + inventory operations — `AdjustableTransactionMixin`,
  `has_invoice=True`, user-driven movements (op_13 / op_14).

Because behavior is preserved, the only spec edits are **registration updates**: the
implementing-code names for the shared engine move to the new mixins. The per-op specs
already name implementing code "as plain names, never links, so renames do not break the
spec" — those references stay valid; only the explicit linked line numbers in
`stock.md` §2.3 need refreshing.

## Current duplication / pain points

### 1. Repeated config block in every stock-event proxy

Four proxy classes repeat the same ~7 config lines:

```python
can_pay = False
check_balance_on_payment = False
is_partially_payable = False
has_category = False
category_required = False
has_repayment = False
has_invoice = True
```

Affected: `op_birth.py`, `op_death.py`, `op_consumption.py`, `op_capital_valuation.py`
(the last is identical except `has_invoice=False` + `has_capital_valuation=True`).
This mirrors the one-shot config duplication already removed in
[`refactor-one-shot-operations-plan.md`](refactor-one-shot-operations-plan.md).

### 2. Inventory behavior buried in the giant `Operation` class

`Operation` is ~1200 lines and mixes core lifecycle code with all inventory behavior:
`inventory_owner_entity`, `inventory_receiving_entity`, `can_create_movement`,
`save_inventory`, `_auto_create_inventory_movements`, `get_items_data`. There is no
single named, documented unit describing "what it means to touch inventory".

### 3. Reversal inventory logic buried in `reverse()`

`Operation.reverse()` (~130 lines) mixes core reversal mechanics with three
type-specific inventory concerns:
- the downstream-movement dependency guard (BIRTH/DEATH/CONSUMPTION/SALE),
- the "reverse all user movements first" guard (PURCHASE/SALE),
- the auto-reverse of tightly-coupled movements (BIRTH/DEATH/CONSUMPTION).

## Proposed design

### A. New `StockEventMixin` in `apps/app_operation/models/operation.py`

```python
class StockEventMixin(BaseModelMixin):
    """Stock-event operations — inventory-only, no accounting transactions.

    Shared config for the auto-movement operations (Birth, Death, Consumption)
    and the value-only capital valuations: never payable, no category, no
    repayment. Invoice-driven by default; ``CapitalValuationOperation``
    overrides ``has_invoice = False`` because it is value-only.
    """

    can_pay = False
    check_balance_on_payment = False
    is_partially_payable = False
    has_category = False
    category_required = False
    has_repayment = False
    has_invoice = True
```

Placed beside the existing composed stacks (`TransactionMixin`,
`OneShotTransactionMixin`, `AdjustableTransactionMixin`, `RepayableTransactionMixin`).

### B. New `InventoryOperationMixin` in `apps/app_operation/models/operation.py`

Extracts the inventory behavior currently inline in `Operation` into one documented
unit, inherited by the lean `Operation` base (so every proxy keeps the methods — views
call `operation.get_items_data()` / `operation.inventory_owner_entity` generically):

```python
class InventoryOperationMixin(BaseModelMixin):
    """Inventory-touching behavior shared by the stock-event and invoice ops.

    Ownership mapping (``inventory_owner_entity`` / ``inventory_receiving_entity``),
    movement eligibility (``can_create_movement``), invoice-item movement summaries
    (``get_items_data``), auto movement creation (``save_inventory`` /
    ``_auto_create_inventory_movements``) and the reversal inventory guards.
    Non-inventory operations get neutral defaults (None / False / empty).
    """
```

Members moved verbatim (behavior-preserving):
- `inventory_owner_entity` (property)
- `inventory_receiving_entity` (property)
- `can_create_movement` (property)
- `save_inventory(bound_formset)`
- `_auto_create_inventory_movements(bound_formset)`
- `get_items_data()`
- `_validate_reversal_inventory_guards()` — extracted from `reverse()`
- `_reverse_inventory_movements(officer, date)` — extracted from `reverse()`

`Operation` then becomes:

```python
class Operation(
    ImmutableMixin,
    AmountCleanMixin,
    OfficerMixin,
    InventoryOperationMixin,
    ReversableModel,
    BaseModel,
):
```

### C. Refactor `Operation.reverse()` to use the extracted hooks

`reverse()` keeps the core reversal mechanics and the accounting/invoice branches, but
calls the two new hooks so the type-specific inventory logic lives in the mixin:

```python
self._validate_reversal_inventory_guards()   # before super().reverse()
...
if type(self).has_invoice:
    self._reverse_inventory_movements(officer, date)  # replaces the PURCHASE/SALE
                                                      # guard + B/D/C auto-reverse
```

### D. Update the stock-event proxies

- `op_birth.py`: `class BirthOperation(StockEventMixin, Operation)` — drop the config
  block; keep `creates_assets = True` and `clean_source`/`clean_destination`.
- `op_death.py`: `class DeathOperation(StockEventMixin, Operation)` — drop the config
  block; keep `clean_source`/`clean_destination`.
- `op_consumption.py`: `class ConsumptionOperation(StockEventMixin, Operation)` — drop
  the config block; keep `project` and `clean_source`/`clean_destination`.
- `op_capital_valuation.py`: `class CapitalValuationOperation(StockEventMixin, Operation)`
  — drop the shared config; keep `has_invoice = False` (override, value-only) +
  `has_capital_valuation = True` and the variant dispatch.

### E. Spec registration edits (provided first, per update-logic rule)

- `docs/specs/features/stock.md` §2.3 — point the shared-engine row at
  `InventoryOperationMixin` / `StockEventMixin` and refresh the linked line numbers
  for `save_inventory` / `_auto_create_inventory_movements`.
- `op_17_birth.md` / `op_18_death.md` / `op_19_consumption.md` — note that the shared
  config block now comes from `StockEventMixin` and the shared engine from
  `InventoryOperationMixin` (plain names, no links).
- `op_5_capital_gain.md` / `op_6_capital_loss.md` — same note for `StockEventMixin`.

## Files to edit

1. `apps/app_operation/models/operation.py` — add `StockEventMixin`,
   `InventoryOperationMixin`; extract inventory methods; refactor `reverse()`.
2. `apps/app_operation/models/proxies/op_birth.py` — use `StockEventMixin`, drop config.
3. `apps/app_operation/models/proxies/op_death.py` — same.
4. `apps/app_operation/models/proxies/op_consumption.py` — same.
5. `apps/app_operation/models/proxies/op_capital_valuation.py` — use `StockEventMixin`,
   drop shared config, keep value-only overrides.
6. `apps/app_operation/tests/test_operation_mixins.py` — structural tests.
7. `docs/specs/features/stock.md` — registration refresh.
8. `docs/specs/operations/op_17_birth.md`, `op_18_death.md`, `op_19_consumption.md`,
   `op_5_capital_gain.md`, `op_6_capital_loss.md` — registration notes.

## Tests

- Existing coverage already pins stock-event behavior:
  `tests/operations/inventory/*`, `tests/operations/purchase/*`,
  `tests/operations/sale/*`, `tests/test_operation_mixins.py`.
- Add structural tests to `tests/test_operation_mixins.py` asserting that:
  - the stock-event proxies inherit the `StockEventMixin` defaults
    (`can_pay=False`, `has_repayment=False`, `has_invoice=True` for B/D/C;
    `has_invoice=False` + `has_capital_valuation=True` for Capital);
  - `Operation` still exposes the inventory API
    (`get_items_data`, `save_inventory`, `inventory_owner_entity`,
    `inventory_receiving_entity`, `can_create_movement`);
  - accounting ops (Purchase/Sale/Expense) are not stock events.
- Run per the testing rules:
  `python3 manage.py test apps.app_operation apps.app_inventory --parallel=10 --keepdb`
  (capture to `tmp/`, then remove the temporary file). No schema change is expected
  (proxies share the concrete `Operation` table); run `--keepdb` and fall back to a
  rebuild only if a model-state change is detected.

## Out of scope

- No behavior change; no migrations expected.
- No changes to the accounting transaction/settlement/repayment mixins.
- No changes to `PurchaseOperation` / `SaleOperation` factory logic beyond what is
  strictly needed to keep them inheriting the same inventory API.

---

## Implementation notes (completed 2026-08-15)

- `apps/app_operation/models/operation.py`
  - Added `InventoryOperationMixin` (before `Operation`) containing all inventory
    behavior moved verbatim: `inventory_owner_entity`, `inventory_receiving_entity`,
    `can_create_movement`, `get_items_data`, `save_inventory`,
    `_auto_create_inventory_movements`, plus the two extracted reversal hooks
    `_validate_reversal_inventory_guards()` and `_reverse_inventory_movements()`.
  - `Operation` now inherits `InventoryOperationMixin` (base order
    `ImmutableMixin, AmountCleanMixin, OfficerMixin, InventoryOperationMixin,
    ReversableModel, BaseModel`); the duplicated inventory methods were removed
    from the class body (the class shrank from ~1206 to ~1110 lines of logic).
  - `Operation.reverse()` now delegates the type-specific inventory logic to the
    two mixin hooks (behavior preserved, comments retained in the mixin).
  - Added `StockEventMixin` beside the composed stacks — shared non-accounting
    config for the stock events.
- Proxies — `op_birth`, `op_death`, `op_consumption`, `op_capital_valuation` now
  inherit `StockEventMixin`; the repeated ~7-line config block was removed.
  `CapitalValuationOperation` keeps `has_invoice = False` (value-only override)
  + `has_capital_valuation = True`.
- Specs — registration updated in `docs/specs/features/stock.md` (§2.3) and
  `op_17_birth.md`, `op_18_death.md`, `op_19_consumption.md`,
  `op_5_capital_gain.md`, `op_6_capital_loss.md` (shared engine now named
  `InventoryOperationMixin` / `StockEventMixin`; plain names kept).
- Tests — `apps/app_operation/tests/test_operation_mixins.py` adds
  `StockEventMixinTest` and `InventoryOperationApiTest`.

**No behavior changed.** Verification:
- `manage.py check` — no issues.
- `manage.py makemigrations --check --dry-run` — no changes detected (proxies only).
- Targeted suite (mixins + inventory/purchase/sale ops + `app_inventory.tests`):
  424 tests OK.
- Full app unit/integration suite (ui_tests excluded per project rules):
  `manage.py test apps.app_base apps.app_entity apps.app_transaction
  apps.app_operation apps.app_adjustment apps.app_inventory apps.app_animal
  --parallel=10 --keepdb` → **1435 tests OK** in ~58s (was 1428; +7 new tests).
