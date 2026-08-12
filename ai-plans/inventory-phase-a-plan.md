# Plan — Inventory Phase A (low-risk reorganization)

**Status:** analysis → plan. Companion to `inventory-app-simplification-analysis.md`.
Deferred (later phases): drop `ProductLedgerEntry`, remove `Product.entity`, Animal/Commodity
split.

**Scope (user-confirmed, 2026-08-12): Phase A only — move `MedicalRecord` out, reconcile
valuation, decouple `Product.status` from operations.**

## 1. Move `MedicalRecord` out of the inventory app

`MedicalRecord` (animal health) is not an inventory concern.

- **New app `app_animal`** (animal-health domain; the future home of the `Animal` model from
  the split). `INSTALLED_APPS` + `apps.py`.
- Move the model into `apps/app_animal/models.py` (unchanged fields; FK to `app_inventory.Product`
  stays — animals are still products until the split).
- **Migration:** create `MedicalRecord` in `app_animal`, remove it from `app_inventory`
  (`apps/app_inventory/migrations/0013_*`), with a **data migration** copying existing rows
  (table rename/copy), keeping `product_id`, `date`, `record_type`, `status`, `next_due_date`,
  `notes`, `officer_id`.
- Move the admin (`MedicalRecordAdmin` + `MedicalRecordInline` in `app_inventory/admin.py`) to
  `app_animal/admin.py`.
- Update [`product_detail.html`](../apps/app_inventory/templates/app_inventory/product_detail.html:354)
  (renders `product.medical_records`) — the related_name survives via the FK.
- Move `MedicalRecordTest` from `test_animal_attributes.py` to `app_animal/tests/`.

## 2. Reconcile valuation (one method)

Today there are two valuation paths that can drift:
- `Product.current_value` = `unit_price × quantity` + capital gain/loss (invoice-items based).
- `ProductLedgerEntry.inventory_value_at` / `state_as_of` = summed movement `value_delta`.

**Change:** make `Product.current_value` equal the movement-based valuation
([`state_as_of(product, today)["value"]`](../apps/app_inventory/models.py:379)), the same basis
the ledger and `app_operation.period` use. This unifies per-product value with entity/period
value. (The `valuation_unit_cost` helper stays as the single carried-cost source.)
- Verify period valuation unchanged (`test_period_model.py`, `test_product_ledger_entry.py`).

## 3. Decouple `Product.status` from operations

Today `Product.status` is derived from the linked `invoice_items` operations (direction-aware).
**Change:** derive it from the product's own **movement lines** + physical presence:

- **ACTIVE** if net presence (incoming − outgoing, non-reversal) > 0.
- **terminal** (`SOLD`/`DEAD`/`CONSUMED`) if net presence ≤ 0 and the last non-reversal outbound
  movement is a SALE/DEATH/CONSUMPTION.
- **REMOVED** if created and all its movements are reversed (no net presence, no terminal).
- Otherwise ACTIVE (e.g. a fresh product with no movements).

This:
- Removes the Product↔Operation coupling (no more `invoice_items` direction-aware logic).
- Naturally distinguishes the internal-transfer buyer copy (has a receipt → ACTIVE) from the
  seller's product (has a dispatch → SOLD).
- Fixes the partial-commodity-sale limitation (remaining presence → ACTIVE).

**Impact:** `validate_active`, product detail, stock views, and many status tests. Keep external
flows unchanged; update/adjust status tests in `test_product.py`, `test_sale_*_reversal.py`,
`test_quick_consume_from_stock.py`, `test_consumption_stock_detail.py`.

## 4. Files

| File | Change |
|---|---|
| `apps/app_animal/` (new) | `apps.py`, `models.py` (`MedicalRecord`), `admin.py`, `tests/`, `migrations/` |
| `apps/app_inventory/models.py` | remove `MedicalRecord`; update `Product.current_value`, `Product.status` |
| `apps/app_inventory/migrations/0013_*` | drop `MedicalRecord`; data migration to `app_animal` |
| `apps/app_inventory/admin.py` | remove `MedicalRecord` admin + inline |
| `apps/app_inventory/templates/app_inventory/product_detail.html` | unchanged behavior (related_name) |
| `farm/settings.py` | add `app_animal` to `INSTALLED_APPS` |

## 5. Verification

- `python manage.py makemigrations app_animal app_inventory && python manage.py migrate`
- `python manage.py check`
- Targeted: `apps/app_animal`, `apps/app_inventory`, sale/reversal/quick-consume/consumption
  tests, `test_period_model.py`.
- Full suite: `manage.py test --parallel=8`.

---

## 6. Implementation status (2026-08-12)

Implemented and verified — full suite green (1441 tests OK via `manage.py test --parallel=8`).

- **`MedicalRecord` moved to the new `apps/app_animal` app**: model, `admin.py`, tests
  (`test_medical_record.py`), and a migration that creates the table in `app_animal` plus a
  data migration in `app_inventory/0013_move_medical_record` (raw-SQL copy then `DeleteModel`).
  `app_animal` added to `INSTALLED_APPS`; `product_detail.html` keeps working via the FK's
  `related_name="medical_records"`.
- **Valuation reconciled:** [`Product.current_value`](../apps/app_inventory/models.py:1251) now
  returns the movement/ledger-based value (`state_as_of` value) for physically-moved products,
  and the nominal carried value for products with no movements — consistent with
  `ProductLedgerEntry.inventory_value_at` / `app_operation.period`. The capital gain/loss
  `current_value` tests were updated to record the ledger entries (the real basis).
- **`Product.status` decoupled from operations:** derived from the product's own movement lines
  + physical presence (net > 0 → ACTIVE; net ≤ 0 with a terminal outbound movement → SOLD/DEAD/
  CONSUMED), with a fallback to the linked-operation status for products with no active
  movements. This **fixes the partial-commodity-sale limitation** (remaining presence stays
  ACTIVE). `save_inventory` now allows the terminal status for DEATH/CONSUMPTION via
  `allow_adjustment` (same hook the movement clean uses).
- **Deferred (later phases):** remove `Product.entity`, Animal/Commodity model split.

---

## 7. Phase B — Drop the product ledger (2026-08-12)

User request: **"Drop the product ledger"**. The `ProductLedgerEntry` table and all its query/
write paths were removed; stock is now computed **directly from `InventoryMovementLine` (the
physical events) + `InvoiceItem`** (contract obligations and capital).

### What changed

- **New module [`apps/app_inventory/stock.py`](../apps/app_inventory/stock.py)** — the single
  source of truth replacing the ledger queries:
  - `movement_state(product, as_of)` → `{quantity, value}` (direction-aware net movement × carried
    cost + active capital gain/loss; reversal-aware).
  - `portfolio(entity, as_of)` — per-product physical presence (qty > 0).
  - `inventory_value(entity, as_of)` — sum of the per-product movement states.
  - `pending_items` / `pending_deliveries(entity, as_of)` — inbound/outbound contract obligations
    derived from `InvoiceItem` vs moved quantity.
  - `capital_delta` excludes **reversed** capital operations (fixes create+reverse invariant).
- **`models.py`**: removed the `ProductLedgerEntry` class; `Product.current_value`,
  `InventoryMovementLine._validate_availability` and the stock queries now use `stock.movement_state`;
  `InventoryMovementLine.save()` no longer writes ledger rows.
- **Call sites** rewired to the stock module: `op_sale`/`op_purchase` (no more `record()`),
  `sale_wizard`, `forms` (`SaleItemForm`), `views` (`stock_detail`/`stock_history`/`quick_consume`/
  `product_detail`), `evaluation` (no more `record()`), `period.py`, `entity_detail.py`,
  `app_adjustment/models.py` (no more `record_adjustment_line`).
- **Deleted** `backfill_product_ledger` command and `test_product_ledger_entry.py`; added
  `apps/app_inventory/tests/test_stock.py` covering the movement-based queries.
- **Migration** `app_inventory/0014_*` drops the `productledgerentry` table.
- Test helpers: `_ledger_totals()` in `apps/app_operation/tests/base.py` is now movement-based,
  keeping the create+reverse differential invariants; `assert_ledger` (unused) removed.
- **Behavior note:** item-adjustment value deltas are no longer tracked separately (deliberate
  simplification); `InvoiceItemAdjustmentLine.quantity_delta`/`value_delta` are still computed
  and tested.

### Verification

- `python manage.py check` — no issues.
- Full suite green: **1435 tests OK** via `manage.py test --parallel=8` (was 1441 before the
  ledger-only test file was replaced).
