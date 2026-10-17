# Financial Period
**App:** `app_operation`
**Model:** `FinancialPeriod`
**Concept:** Tracks open/closed accounting periods per entity. Each operation is assigned to the entity's open period at creation time. Periods can be closed (setting an `end_date`), which automatically opens a new period for active entities.

---

## Model fields

| Field        | Type            | Notes                                              |
|--------------|-----------------|----------------------------------------------------|
| `entity`     | FK → Entity     | Immutable after save                               |
| `start_date` | DateField       | Immutable after save; auto-set to the entity's `start_date` for the first period (falling back to the creation date), or to the close date of the previous period |
| `end_date`   | DateField       | Null = open. Set via `close(end_date)`. Immutable once set. |

**Computed:**
- `is_closed`: `end_date is not None and end_date < today`

**Auto-creation:** A `FinancialPeriod` is automatically created via a post-save signal when a Person or Project entity is created. The first period's `start_date` comes from the entity's `start_date` (set from the create form's Start Date field, default today); when the entity has no start date it falls back to the creation date. World and System entities do not get periods.

**Operation assignment:** Operations are auto-assigned to the destination entity's open period at creation. Reversals are exempt (can be recorded even in/after a closed period).

**Computed valuation (`FinancialPeriod`):**
- `end_assets` = cash balance (`payment_types()` incoming − outgoing) + **movement-based inventory value** ([`inventory_value()`](../../../apps/app_inventory/stock.py)) + outstanding loan credits + outstanding worker advances paid.
- Inventory value is movement-based: net quantity × carried unit cost + capital gain/loss ([`movement_state()`](../../../apps/app_inventory/stock.py)).
- Birth / Death / Capital Gain / Capital Loss are **non-cash**: their `*_PAYMENT` transactions are excluded from `payment_types()`, so their value is reflected **exactly once**, in inventory — never in the cash balance. A sale is valued at carried cost, so `end_assets` correctly reflects profit (sale − carried cost).
- `remaining_inventory_value` (operation-based) is no longer used by `end_assets`.

---

## Validation

- `start_date` is immutable after save
- `entity` is immutable after save
- The entity's `start_date` (which seeds the first period) cannot be in the future
- `end_date` is immutable once set (cannot change a closed period's end date)
- `close(end_date)` raises if `end_date < start_date`
- `close(end_date)` raises if the period is already closed
- Only one open period (no `end_date`) per entity at a time
- Periods for the same entity must not overlap (`start_date`/`end_date` ranges)
- Non-overlapping sequential periods for the same entity are allowed
