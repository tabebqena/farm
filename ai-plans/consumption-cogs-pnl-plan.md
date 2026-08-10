# Plan — Consumption as COGS on the Project P&L

**Status:** Implemented — **Option B** (COGS as a P&L cost, consumption made non-cash).
**Date:** 2026-08-10
**Parent:** [`ai-plans/consumption-vs-expense-analysis.md`](consumption-vs-expense-analysis.md) (deferred item, user decision: separate plan).
**Scope:** `apps/app_transaction/transaction_type.py`, `apps/app_entity/models/__init__.py`, `apps/app_operation/models/period.py`, consumption tests + spec.

---

## 1. Goal

Recognize consumed feed/medicine as a **Cost of Goods Sold (COGS)** that reduces the **project's own profit** in the period it is consumed — matching feed cost to the period of the milk/meat revenue it helps produce — instead of the current `project → system` write-off that never touches the P&L.

---

## 2. Current behavior (write-off model)

When feed is consumed, [`ConsumptionOperation`](../apps/app_operation/models/proxies/op_consumption.py) writes two transactions, both `project → system` ([`transaction_type.py:548`](../apps/app_transaction/transaction_type.py:548)):

- `CONSUMPTION_ISSUANCE` (non-cash) + `CONSUMPTION_PAYMENT` (cash-type).

Consequences:

1. [`CONSUMPTION_PAYMENT`](apps/app_transaction/transaction_type.py:320) is a payment-type tx, so [`Entity.balance_at()`](../apps/app_entity/models/__init__.py:414) reduces the project fund balance by the consumed value (drain to a virtual system account).
2. [`Entity.profit_loss()`](../apps/app_entity/models/__init__.py:539) does **not** list CONSUMPTION among its costs ([`__init__.py:617`](../apps/app_entity/models/__init__.py:617)), so the P&L never reflects the consumed feed.
3. Net effect today: feed cost hits the P&L at **purchase** (as buyer), and consumption then drains the balance a **second time** without appearing as a cost — so reported profit is overstated relative to real input cost.

---

## 3. Design decision (choose one)

### Option A — COGS as a P&L cost, keep the write-off for balance (minimal)
Add `CONSUMPTION_ISSUANCE` to the **costs** list in [`Entity.profit_loss()`](../apps/app_entity/models/__init__.py:617). Consumption then reduces profit (COGS), while the existing `project → system` payment continues to drain the balance.

- ✅ Minimal change; consumption now shows in P&L and period `amount`.
- ❌ Balance is still drained by a virtual system payment — double-counting remains between P&L (cost) and balance (asset outflow). `end_assets` (which already subtracts consumption via the valuation fix) plus the balance drain may double-count the reduction.

### Option B — COGS as P&L cost, make consumption non-cash (recommended)
- Add `CONSUMPTION_ISSUANCE` to `profit_loss()` costs.
- **Remove `CONSUMPTION_PAYMENT` from the payment-type set** so it no longer drains the fund balance ([`TransactionType.payment_types()`](../apps/app_transaction/transaction_type.py:440)).
- The consumed value then moves from the **inventory asset** (ledger, already subtracted by the valuation fix) to **COGS on the P&L** — a clean internal transfer on the project's own books, no virtual system entity.

- ✅ Correct accrual/matching: purchase capitalizes, consumption expenses.
- ✅ `end_assets` (cash balance + inventory) and P&L both reflect consumption exactly once.
- ❌ Larger change: affects `balance_at()`, period balance displays, and existing consumption tests that assert the `project → system` payment.

### Option C — Separate COGS transaction type (most explicit)
Introduce a dedicated `CONSUMPTION_COGS` issuance (non-cash) that `profit_loss()` counts, alongside or replacing the current issuance/payment pair.

- ✅ Cleanest semantics.
- ❌ New transaction type + migration + mapping + tests — most work.

**Recommendation:** Option B, unless the team wants to preserve the `project → system` balance trail (then Option A).

---

## 3.5 "Why not just remove the Consumption payment type?" — effects

There are two different things "removing the payment type" could mean. Only the first is cheap.

### A) Remove `CONSUMPTION_PAYMENT` from `payment_types()` — keep creating it (Option B, recommended)

This is the minimal interpretation, and it is what Option B already proposes:

- [`TransactionType.payment_types()`](../apps/app_transaction/transaction_type.py:440) no longer lists `CONSUMPTION_PAYMENT`.
- [`Entity.balance_at()`](../apps/app_entity/models/__init__.py:414) stops draining the project fund on consumption (no virtual `project → system` cash out).
- [`FinancialPeriod.cash_out` / `end_assets`](../apps/app_operation/models/period.py:277) no longer count the payment; consumption is then reflected **exactly once** via `remaining_inventory_value` (which already subtracts consumption).
- **Settlement bookkeeping is unaffected**: `amount_settled` / `is_fully_settled` / `amount_remaining_to_settle` filter by `_payment_transaction_type` directly ([`mixins.py:281`](../apps/app_base/mixins.py:281)), not by `payment_types()`, so the op still appears fully settled and the detail view still lists the (non-cash) payment row.
- Existing tests that assert the issuance+payment pair exist keep passing; only balance/period tests change.

### B) Stop creating `CONSUMPTION_PAYMENT` transactions at all (or delete the constant)

This is **more invasive, not less**, and does not by itself fix the P&L:

1. `ConsumptionOperation` is a **one-shot** operation ([`op_consumption.py:30`](../apps/app_operation/models/proxies/op_consumption.py:30)). The one-shot `save()` path requires a payment type — with `_payment_transaction_type = None`, `_has_single_payment_transaction` is False and `save()` raises `ValidationError("This record can't act as a one-shot operation record")` ([`mixins.py:439`](../apps/app_base/mixins.py:439)). We would have to drop `_is_one_shot_operation` too.
2. **Settlement UI breaks**: `amount_settled` → 0, `is_fully_settled` → False, `amount_remaining_to_settle` → full amount. The detail view ([`detail.py:89`](../apps/app_operation/views/detail.py:89)) would show consumption as permanently unpaid/outstanding.
3. **Reversal tests break**: `test_reverse_creates_counter_transactions` expects 2 counter-transactions; with no payment there is only 1.
4. If the `CONSUMPTION_PAYMENT` **constant** is also deleted: needs removal from `_TX_ENTITY_TYPE_MAP` ([`transaction_type.py:549`](../apps/app_transaction/transaction_type.py:549)) and `_TX_OPERATION_MAP` ([`:632`](../apps/app_transaction/transaction_type.py:632)), plus handling of pre-existing `CONSUMPTION_PAYMENT` rows that would no longer match `choices`.
5. It still does **not** add consumption to the P&L — `profit_loss()` reads issuance types only, so the separate `profit_loss()` change is required regardless.

**Verdict:** "Removing the Consumption payment type" in the sense that matters = Option B (drop it from `payment_types()`). Fully deleting the payment transaction is strictly more work, breaks settlement/reversal, and adds no P&L benefit — reject.

---

## 4. Implementation steps

1. **Decide Option A vs B** (§3) with the user.
2. **`profit_loss()` change** — add `TransactionType.CONSUMPTION_ISSUANCE` to the costs `type__in` list in [`Entity.profit_loss()`](../apps/app_entity/models/__init__.py:617).
   - For Option B only: remove `CONSUMPTION_PAYMENT` from [`payment_types()`](../apps/app_transaction/transaction_type.py:440) so `balance_at()` no longer drains the fund on consumption.
3. **Valuation consistency** — confirm [`remaining_inventory_value`](../apps/app_operation/models/period.py:362) (already subtracts consumption) + balance + P&L each reflect consumption exactly once. Add a reconciliation test.
4. **Reversal** — verify consumption reversal negates the COGS effect (reversal clone of `CONSUMPTION_ISSUANCE` must restore profit). Update [`record()`](../apps/app_inventory/models.py:153) / movement reversal paths if needed.
5. **Specs** — update [`specs/operations/op_19_consumption.md`](../specs/operations/op_19_consumption.md) and the operations comparison (§19) to document the new accounting.
6. **Tests** — update `test_consumption_consumption_create.py` / `_reversal.py` (they assert the current issuance+payment flow) and `test_distribution_plan_period_profit_loss_properties.py` (period `amount`). Add:
   - Consumption reduces `Entity.profit_loss()` in the consumption period.
   - `FinancialPeriod.amount` (closed period) reflects consumed feed as a cost.
   - (Option B) `balance_at()` is **unchanged** by consumption; `end_assets` still decreases via inventory.

---

## 5. Verification

- `python manage.py test apps.app_operation.tests.operations.inventory apps.app_operation.tests.period --parallel=4`
- `python manage.py check`

---

## 6. Implementation status

**Option B implemented.** Status: **Done.**

### What was implemented

- **`profit_loss()` COGS** — added `CONSUMPTION_ISSUANCE` to the costs `type__in` list in
  [`Entity.profit_loss()`](../apps/app_entity/models/__init__.py), so consumption reduces the
  project's P&L in the consumption period.
- **Non-cash consumption** — removed `CONSUMPTION_PAYMENT` from
  [`TransactionType.payment_types()`](../apps/app_transaction/transaction_type.py). The payment
  transaction is still created (settlement bookkeeping unaffected), but `balance_at()`,
  `FinancialPeriod.cash_out`, `end_balance` and `end_assets` no longer drain the fund on
  consumption. `end_assets` reflects consumption exactly once via `remaining_inventory_value`.
- **Reversal** — a reversal of a consumption is a mirror transaction (`source↔target` swapped),
  so `profit_loss()` now also sums `target=fund` `CONSUMPTION_ISSUANCE` transactions (negated by
  `_signed_sum`) to negate the COGS and restore profit.
- **Specs** — updated [`specs/operations/op_19_consumption.md`](../specs/operations/op_19_consumption.md)
  (added "P&L / Accounting (COGS, Option B)") and the §19 entry in
  [`specs/operations/operations-comparison.md`](../specs/operations/operations-comparison.md).

### Tests added / updated

- `test_consumption_consumption_create.py`:
  - `test_create_reduces_profit_loss` — consumption lowers `Entity.profit_loss()` by the consumed value.
  - `test_create_does_not_drain_fund_balance` — `balance_at()` unchanged by consumption.
- `test_consumption_consumption_reversal.py`:
  - `test_reverse_restores_profit_loss` — reversal negates the COGS (profit restored).
  - `test_reverse_keeps_fund_balance_unchanged` — reversal does not change the fund balance.
- `test_period_model.py`:
  - `test_consumption_reflected_exactly_once_in_end_assets` — consumption does not change the fund
    balance and reduces `end_assets` exactly once via inventory.
- `test_distribution_plan_period_profit_loss_properties.py`:
  - `PeriodAmountReflectsConsumptionTest` — a closed period's `amount` includes consumed feed as a
    COGS cost, and the fund balance is unchanged.

### Verification

- `python manage.py test apps.app_operation.tests.operations.inventory apps.app_operation.tests.period --parallel=4` → 137 passed.
- `python manage.py test --parallel=4` → 1215 passed.
- `python manage.py check` → no issues.
