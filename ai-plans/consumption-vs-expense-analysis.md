# Analysis & Decision — Consumption vs. Expense for non-animal items

**Status:** Decision pending — analysis only, no code changes yet.
**Date:** 2026-08-10
**Scope:** `apps/app_inventory/models.py`, `apps/app_operation/models/proxies/op_consumption.py`, `apps/app_operation/models/proxies/op_expense.py`, `apps/app_operation/models/period.py`

---

## 1. Context

The app tracks a livestock business. The farm:

- Purchases animals (cows, goats) into inventory.
- Sells animals and their products (e.g. milk, meat).
- Needs to report consumed inputs (feed, corn, medications).
- Wants accurate **project valuation**.

To cover animals + feed + medicine with one abstraction, `ProductTemplate` was made broad:

- [`ProductTemplate.Nature`](apps/app_inventory/models.py:514): `ANIMAL`, `FEED`, `MEDICINE`, `PRODUCT`.
- [`ProductTemplate._ALLOWED_OP_TYPES`](apps/app_inventory/models.py:561): `FEED`/`MEDICINE` allow `PURCHASE`, `SALE`, `CONSUMPTION`, `CAPITAL_GAIN`, `CAPITAL_LOSS`.

The **Consumption** operation was created to remove feed/medicine from inventory:

- [`ConsumptionOperation`](apps/app_operation/models/proxies/op_consumption.py:7): `project → system`, one-shot, auto-creates movement lines.
- Writes `CONSUMPTION_MOVEMENT` ledger entries at carried cost ([`valuation_unit_cost()`](apps/app_inventory/models.py:21)) and marks the product `CONSUMED` ([`Product.Status`](apps/app_inventory/models.py:811)).
- Spec: [`specs/operations/op_19_consumption.md`](../specs/operations/op_19_consumption.md).

The **Expense** operation was proposed as an alternative for tracking all non-animal items:

- [`ExpenseOperation`](apps/app_operation/models/proxies/op_expense.py:7): `project → world`, category required (`EXPENSE` type), partially payable, **no inventory / no ledger**.
- Spec: [`specs/operations/op_12_expense.md`](../specs/operations/op_12_expense.md).

**Open question:** should the user track all non-animal items (feed, medicine, corn) as **Expenses only**, instead of through the Consumption operation?

---

## 2. The two designs

| Aspect | A. Consumption (inventory) — current | B. Expense-only for non-animals — proposed |
|---|---|---|
| Feed bought | PURCHASE → inventory asset, ledger entry | EXPENSE op → immediate cost, no inventory |
| Feed used | CONSUMPTION → write-off at carried cost, product `CONSUMED` | n/a |
| Stock on hand | Knowable (ledger `state_as_of` / `portfolio_as_of`) | Not knowable |
| Consumption analytics | Per-item, per-period usage | Only "how much was bought" |
| Project valuation | Feed in shed counts as an asset until used | Feed value drops to zero at purchase |
| User effort | Two-step (purchase+receive, then consume) | One step |
| Recording errors | Higher (ambiguous path) | Lower (single path) |

---

## 3. Valuation impact (the user's stated goal)

Project valuation lives in [`FinancialPeriod.end_assets`](apps/app_operation/models/period.py:418):

```
end_assets = cash balance
           + remaining_inventory_value
           + outstanding loan credits
           + outstanding worker advances paid
```

`remaining_inventory_value` = total PURCHASE amounts − total SALE amounts ([`period.py:363`](apps/app_operation/models/period.py:363)).

Tracing "buy 5,000 SAR of corn":

| Moment | Consumption model | Expense-only model |
|---|---|---|
| Buy corn | cash −5,000, inventory +5,000 → **assets flat** | cash −5,000 → **assets −5,000** |
| Feed corn later | inventory −5,000 → assets drop when actually used | *(already expensed)* |

**Finding:** Expense-only understates project value the moment feed is bought, even though the physical feed is still on hand. For the valuation goal, stockable consumables must stay in inventory.

---

## 4. Comparison against accounting principles

| Principle | Consumption (inventory) | Expense-only | Verdict |
|---|---|---|---|
| **Accrual vs cash** | Cost recognized when used (accrual) | Cost recognized when cash paid (cash-basis) | Consumption wins |
| **Matching** | Feed cost matched to the period of milk/meat revenue | Feed cost booked months before related revenue | Consumption wins |
| **Asset vs expense** | Feed/medicine in stock = future benefit → capitalize then expense on use | Expensing a genuine asset on purchase | Consumption wins |
| **COGS** | Consumption = cost of livestock inputs used, enables gross margin | All feed purchases lumped into operating expense | Consumption wins |
| **Consistency** | Ambiguous — same item can be Consumption or Expense today (violates) | Single path, consistent | Expense-only wins (but see fix below) |
| **Materiality** | Overkill for tiny/instant consumables | Correct for immaterial, instantly-used items | Expense-only wins (for that subset) |
| **IAS 41 (Agriculture)** | Distinguishes consumable vs bearer assets; inputs consumed are COGS | Treats inputs as immediate expense | Consumption wins |

**Conclusion:** accounting principles **decisively favor keeping Consumption for stockable consumables** (feed/medicine) and using Expenses only for immaterial or non-stocked items — a **hybrid, nature-driven** model. Expense-only for feed violates accrual, matching, and capitalize-vs-expense rules and undermines project valuation.

Caveat: today consumption is booked as a write-off `project → system`, not as **COGS reducing the project's own profit**. For proper matching-based P&L, consumption should be recognized as a cost on the project (tied to the valuation fix in §5).

---

## 5. Confirmed gaps / bugs

1. **Valuation bug — `end_assets` ignores consumption and death.**
   [`remaining_inventory_value`](apps/app_operation/models/period.py:363) = purchases − sales only; it never subtracts CONSUMPTION or DEATH. After feed is consumed (or an animal dies), `end_assets` still counts it as on-hand → **project value overstated**. The ledger-based [`inventory_value`](apps/app_operation/models/period.py:356) gets it right but is **not** the value used in `end_assets`.

2. **No production path for `PRODUCT` nature (milk, meat).**
   Milk and Meat are seeded as `nature=PRODUCT` ([`seed.py:95`](apps/app_base/management/commands/seed.py:95)), but `PRODUCT` allows only `PURCHASE`/`SALE`/`CAPITAL_*`. There is **no operation that creates production output**, so milk can only "enter" inventory by being (incorrectly) purchased. This is the real gap behind "sell animals or its products like milk".

3. **Expense-vs-consumption ambiguity (consistency violation).**
   The same physical item (e.g. corn) can be recorded either as an inventory Consumption write-off or as a plain Expense. This ambiguity is the root cause of the farmer's "wrong decisions". The boundary must be **enforced by nature**, not left to user judgment.

4. **Friction.** The correct flow (purchase+receive, then separate Consumption op) is heavy for daily feeding, which pushes the farmer toward the shortcut (Expense).

---

## 6. Recommendation (hybrid, nature-driven)

1. **Keep Consumption** for stockable consumables: `FEED`, `MEDICINE` (assets until used; needed for valuation and consumption analytics).
2. **Use Expense** only for non-stocked / immaterial items (vet services, transport, utilities, wages).
3. **Fix `end_assets`** to subtract CONSUMPTION/DEATH — derive inventory value from the ledger ([`ProductLedgerEntry.inventory_value_at`](apps/app_inventory/models.py:405)), or subtract consumption/death amounts from `remaining_inventory_value`.
4. **Enforce the boundary:** prevent `FEED`/`MEDICINE` from being recorded as plain Expense (e.g. route by nature, or validate at the Expense form/model level).
5. **Add a production/output path** for `PRODUCT` nature so milk/meat can enter inventory and then be sold.
6. **Reduce friction:** a one-step "consume from stock" path so daily feeding is one action, not two operations.

---

## 7. Open decisions

- [*] Confirm direction: hybrid (recommended) vs. expense-only for non-animals.
User Decision: Approved, leave hybrid.
- [ ] Whether consumption should be COGS on the project P&L instead of a `project → system` write-off.
  - **Current (write-off):** `CONSUMPTION_ISSUANCE` + `CONSUMPTION_PAYMENT` both flow `project → system` ([`transaction_type.py:548`](../apps/app_transaction/transaction_type.py:548)). `CONSUMPTION_PAYMENT` is a payment-type tx, so it reduces the project fund balance via [`Entity.balance_at()`](../apps/app_entity/models/__init__.py:414). But [`Entity.profit_loss()`](../apps/app_entity/models/__init__.py:539) does **not** list CONSUMPTION among its costs ([`__init__.py:617`](../apps/app_entity/models/__init__.py:617)). Net effect: feed cost hits the P&L at *purchase* (as buyer), and consumption then drains the balance a second time without appearing as a P&L cost.
  - **Proposed (COGS):** recognize consumed feed/medicine as a cost reducing the project's own profit in the period consumed (matching feed to milk/meat revenue), and reduce the inventory asset — no `project → system` payment draining the balance. P&L becomes: revenue − COGS − operating expenses.
  - **Why it's open:** changes `profit_loss()` and consumption/reversal transaction behavior (existing tests assert the current flow), and interacts with the valuation fix in §5.1 (end_assets must subtract consumption regardless).
User Decision:
User Decisoion:
   - Put a seperate plan.
- [*] Valuation method for the ledger: carried cost today; moving-average/FIFO/fair value (IAS 41) later.
   User Decision:. use the purchase value

---

## 8. Implementation status

*(Per repo convention, what was actually implemented.)*

**Implemented (2026-08-10):**

- [x] **Valuation fix — `end_assets` now subtracts CONSUMPTION and DEATH.**
  - [`FinancialPeriod.remaining_inventory_value`](apps/app_operation/models/period.py:362) now subtracts CONSUMPTION and DEATH operation amounts in addition to PURCHASE − SALE, so a closed period's `end_assets` no longer counts stock that was consumed or written off as still on hand. Valuation stays at the **purchase (carried) cost** per the user decision.
- [x] **Test: valuation fix.**
  - Added `RemainingInventoryValueTest` in [`apps/app_operation/tests/period/test_period_model.py`](../apps/app_operation/tests/period/test_period_model.py) — verifies consumption, death, both, and reversal-exclusion (`reversal_of` clones are not double-counted). 4 tests.
- [x] **Boundary guidance (Expense vs. Consumption).**
  - [`snippets/create-form/category.html`](../apps/app_operation/templates/app_operation/snippets/create-form/category.html) now shows a note on the Expense form: stockable inputs (feed/medicine/corn) should use Purchase + Consumption so they remain tracked in inventory.
- [x] **Test: available products vs. inventory value.**
  - Added `test_available_products_and_value_after_death_consumption_sale` in [`apps/app_inventory/tests/test_product_ledger_entry.py`](../apps/app_inventory/tests/test_product_ledger_entry.py) — proves `portfolio_as_of` returns only on-hand stock (fully SOLD/DEAD/CONSUMED products excluded) and `inventory_value_at` equals only the remaining value.

**Verification:** `manage.py test apps.app_operation.tests.period apps.app_operation.tests.operations.inventory apps.app_inventory.tests.test_product_ledger_entry apps.app_inventory.tests.test_product --parallel=4` → all pass (130 + 17 + 36).

**Deferred — separate plans (not implemented here):**
- [x] Consumption as COGS on the project P&L (user decision: separate plan) → [`consumption-cogs-pnl-plan.md`](consumption-cogs-pnl-plan.md).
- [ ] Production/output path for `PRODUCT` nature (milk, meat) to enter inventory → [`production-output-path-plan.md`](production-output-path-plan.md).
- [x] One-step "consume from stock" friction reduction → [`consume-from-stock-plan.md`](consume-from-stock-plan.md).
- [x] Hard block preventing FEED/MEDICINE from being recorded as Expense → [`expense-stockable-block-plan.md`](expense-stockable-block-plan.md).
