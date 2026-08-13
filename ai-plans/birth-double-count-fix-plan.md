# Plan: Fix the Birth double-count (end_assets → movement inventory + declassify virtual payments)

## IMPLEMENTED (2026-08-13)

- Spec edits applied: [`specs/operations/op_17_birth.md`](../specs/operations/op_17_birth.md),
  [`op_18_death.md`](../specs/operations/op_18_death.md), [`op_5_capital_gain.md`](../specs/operations/op_5_capital_gain.md),
  [`op_6_capital_loss.md`](../specs/operations/op_6_capital_loss.md),
  [`operations-comparison.md`](../specs/operations/operations-comparison.md), [`financial_period.md`](../specs/features/financial_period.md)
  — all document the non-cash `*_PAYMENT` classification and the movement-based `end_assets`.
- [`apps/app_transaction/transaction_type.py`](../apps/app_transaction/transaction_type.py): removed
  `BIRTH_PAYMENT`, `DEATH_PAYMENT`, `CAPITAL_GAIN_PAYMENT`, `CAPITAL_LOSS_PAYMENT` from `payment_types()` (kept the type constants and maps).
- [`apps/app_operation/models/period.py`](../apps/app_operation/models/period.py): `end_assets` now uses
  `inventory_value(entity, end_date)` (movement-based); deleted the now-unused `remaining_inventory_value` property.
- Tests:
  - [`test_period_model.py`](../apps/app_operation/tests/period/test_period_model.py): replaced `RemainingInventoryValueTest`
    with `EndAssetsMovementValueTest` (movement-based end_assets for birth/consumption/death/capital gain/capital loss/sale).
  - Capital gain/loss tests updated: fund balance unchanged (non-cash) for create + reversal; the "deficit" loss tests
    now assert non-cash behavior (balance unchanged, no deficit created).
  - `CoverageManifestTest` references updated to the renamed test methods.
  - Ripple fix: every test helper that seeded a project's *spendable* balance via `CapitalGainOperation`
    (`inject_project_fund`, `_inject_funds` in transaction/operation-create-view tests, the 6 distribution
    `_seed_capital_gain` helpers, `_inject_project` in purchase-create tests) now seeds real cash via
    `CorrectionCreditOperation` (its payment is still a real payment type). Type-specific assertions switched from
    `CAPITAL_GAIN_PAYMENT` to `CORRECTION_CREDIT_PAYMENT` where needed.
- Verification: full suite `1448` tests pass; `python manage.py check` clean.

## Problem (confirmed)

A birth of value X currently records the born animal **twice** in any "cash + stock" total:

| Metric | Effect | Root cause |
|---|---|---|
| Project cash balance | +X | `BIRTH_PAYMENT` is in [`payment_types()`](apps/app_transaction/transaction_type.py:418) → [`balance_at()`](apps/app_entity/models/__init__.py:414) credits the project |
| Movement-based stock value | +X | BIRTH is inbound in [`stock.py`](apps/app_inventory/stock.py:13) → [`inventory_value()`](apps/app_inventory/stock.py:143) |
| `profit_loss` | 0 | BIRTH types not in income/costs lists |
| `remaining_inventory_value` | 0 | only sums PURCHASE/SALE/CONSUMPTION/DEATH |
| `end_assets` | +X | via cash only (birth excluded from `remaining_inventory_value`) |

**Precedent:** [`ConsumptionOperation`](apps/app_operation/models/proxies/op_consumption.py:16) already does it right — `CONSUMPTION_PAYMENT` is created but is **not** in `payment_types()` (non-cash). Birth/Death/Capital deviated.

## Confirmed decision (user)

- **Model A**: virtual value ops (Birth/Death/Capital Gain/Capital Loss) are **non-cash**; their value lives only in inventory (movement-based).
- **Option 2a**: keep the payment transactions (for settlement/reversal/audit) but **remove `BIRTH_PAYMENT`, `DEATH_PAYMENT`, `CAPITAL_GAIN_PAYMENT`, `CAPITAL_LOSS_PAYMENT` from `payment_types()`**.
- **Do it in one pass** so `end_assets` is consistent for all four ops.

## Change 1 — `end_assets` uses movement-based inventory value

**File:** [`apps/app_operation/models/period.py`](apps/app_operation/models/period.py:435)

Replace `self.remaining_inventory_value` with `inventory_value(self.entity, self.end_date)`.

```python
@property
def end_assets(self) -> Optional[Decimal]:
    if self.end_date is None:
        return None
    from apps.app_transaction.transaction_type import TransactionType
    from apps.app_inventory.stock import inventory_value

    balance: Decimal = self._incoming_tx_sum(
        TransactionType.payment_types(), self.end_date
    ) - self._outgoing_tx_sum(TransactionType.payment_types(), self.end_date)
    return (
        balance
        + inventory_value(self.entity, self.end_date)
        + self.outstanding_loan_credited
        + self.outstanding_worker_advance_paid
    )
```

Side effect on other ops:
- Purchase: net 0 (unchanged).
- **Sale: fixes a latent bug** — old formula subtracted the sale *price* from `remaining_inventory_value`, so `end_assets` never reflected profit; movement-based subtracts the *carried cost*, so `end_assets` change = sale − carried cost = profit.
- Consumption: unchanged (already non-cash).
- Death / Capital Gain / Capital Loss: only correct once Change 2 lands (else double-counted).

## Change 2 — declassify virtual payments from `payment_types()`

**File:** [`apps/app_transaction/transaction_type.py`](apps/app_transaction/transaction_type.py:418)

Remove these four entries from the `payment_types()` frozenset:
- `cls.BIRTH_PAYMENT`
- `cls.DEATH_PAYMENT`
- `cls.CAPITAL_GAIN_PAYMENT`
- `cls.CAPITAL_LOSS_PAYMENT`

Keep the type constants, the `_build_tx_entity_type_map` entries, and the `_OP_TX_TYPES` map (lines ~542-545, 626-629) — they remain valid for legacy rows and reversal mirror transactions.

**Impact of the `payment_types()` change** (all share the same frozenset):
- [`Entity.balance_at()`](apps/app_entity/models/__init__.py:414) — fund balance no longer includes the four virtual flows (becomes purely cash-based).
- [`FinancialPeriod.end_assets`](apps/app_operation/models/period.py:435) — balance component drops them.
- [`FinancialPeriod.balance`](apps/app_operation/models/period.py:273) and the period ledger view ([`views/period.py`](apps/app_operation/views/period.py:232)) — no longer list them as cash.
- Entity payment-transactions list ([`views.py`](apps/app_transaction/views.py:47)) — no longer lists them as cash movements.

## Resulting numbers (birth of 5 @ 100 = 500)

| Measure | Before | After (Change 1 + 2) |
|---|---|---|
| Cash balance | +500 | **+0** |
| Movement stock value | +500 | **+500** |
| `end_assets` | +500 (as cash) | **+500 (as inventory)** |
| `profit_loss` | 0 | 0 |
| Born counted in cash+stock | **twice** | **once** |

## Cleanup: `remaining_inventory_value`

After Change 1, [`remaining_inventory_value`](apps/app_operation/models/period.py:363) has no consumer (only `end_assets` used it). Recommended: **delete the property** to eliminate the second, drifting valuation source. Its only references are the property itself + `RemainingInventoryValueTest` (which gets rewritten below).

## Test changes

**⚠ Gotcha:** `make_operation` (in [`tests/general.py`](apps/app_inventory/tests/general.py:44)) calls the Django base `Model.save()` directly, bypassing the mixin save chains — so it creates **no transactions and no movement lines**. Any test that asserts movement-based `end_assets` behavior must drive the **full create pipeline** (e.g. `PurchaseOperation.create(...)` with a formset, or explicit `InventoryMovementLine` creation), not `make_operation`.

- [`apps/app_operation/tests/period/test_period_model.py`](apps/app_operation/tests/period/test_period_model.py:251) `RemainingInventoryValueTest`:
  - Rewrite to build real movements and assert movement-based `end_assets`:
    - purchase → `end_assets` unchanged (cash −X, inventory +X)
    - sale → `end_assets` += sale − carried cost
    - consumption → `end_assets` −= consumed carried cost (once)
    - **birth** → `end_assets` += born value exactly once, and **cash balance unchanged**
    - death → `end_assets` −= dead carried cost exactly once, cash unchanged
    - capital gain/loss → `end_assets` ±= value, cash unchanged
  - Delete the `remaining_inventory_value` assertions.
  - Keep/adapt `test_consumption_reflected_exactly_once_in_end_assets` (needs movements now).
- Birth create/reversal tests ([`test_birth_birth_create.py`](apps/app_operation/tests/operations/birth/test_birth_birth_create.py:108), [`test_birth_birth_reversal.py`](apps/app_operation/tests/operations/birth/test_birth_birth_reversal.py:90)) — **unchanged** (payment tx still created under 2a).
- Death/capital create tests — add/keep assertions that the project cash balance is **unaffected** by death/capital (non-cash), while inventory value changes.
- Entity detail / transaction-list tests if balance semantics assertions exist.

## Spec edits (spec first, per repo rule)

### [`specs/operations/op_17_birth.md`](specs/operations/op_17_birth.md:5)
- **Transaction flow:** annotate payment as non-cash: `Payment: system.fund → project — type BIRTH_PAYMENT (non-cash bookkeeping; not balance-affecting)`.
- **Success effects:** update "Fund deltas" to `no cash flow — ▼ system (virtual, non-cash) → ▲ project assets`; add a line: `the born animal's value is carried once, in inventory value (movement-based), never in the cash balance or P&L`.
- Add a **Valuation / double-count note** section: `end_assets` = cash + movement-based inventory; a birth increases `end_assets` exactly once, via inventory.

### [`specs/operations/op_18_death.md`](specs/operations/op_18_death.md:5)
- Same treatment: `DEATH_PAYMENT` is non-cash bookkeeping; death reduces `end_assets` exactly once, via inventory.

### [`specs/operations/op_5_capital_gain.md`](specs/operations/op_5_capital_gain.md:4)
- `CAPITAL_GAIN_PAYMENT` non-cash bookkeeping; gain value reflected once in inventory (`capital_delta`) and once in `profit_loss` (income) — `end_assets` increase equals the recognized gain.

### [`specs/operations/op_6_capital_loss.md`](specs/operations/op_6_capital_loss.md:4)
- Same: `CAPITAL_LOSS_PAYMENT` non-cash; loss reflected once in inventory and once in `profit_loss` (cost).

### [`specs/operations/operations-comparison.md`](specs/operations/operations-comparison.md:243)
- Birth/Death/Capital rows: note the non-cash payment classification and the movement-based `end_assets` valuation.

### [`specs/features/financial_period.md`](specs/features/financial_period.md)
- `end_assets` definition: `cash balance + movement-based inventory value + outstanding loan credits + outstanding worker advances paid`.

## Implementation order (for code mode)

1. [`transaction_type.py`](apps/app_transaction/transaction_type.py:418) — remove the 4 payment types from `payment_types()`.
2. [`period.py`](apps/app_operation/models/period.py:435) — `end_assets` uses `inventory_value(entity, end_date)`.
3. [`period.py`](apps/app_operation/models/period.py:363) — remove `remaining_inventory_value` (and its import-time dependencies if unused).
4. Rewrite `RemainingInventoryValueTest` + related period tests using the full create pipeline (real movements).
5. Update death/capital/entity-detail tests for the non-cash semantics.
6. Apply spec edits.
7. Verify: `python manage.py check`, targeted `pytest` for period, birth, death, consumption, capital, entity-detail.
