# Plan: Purchased animal must create one product line per head when a movement is registered

**Status:** Implemented — see Implementation log below.

## Contract (verified)

The product-line contract is: **one product line per purchased animal** — if the
user purchased 10, **10 lines are created, each with quantity 1**, and each line
lazy-creates its own tagged `Product`.

This already held in:

- [`PurchaseOperation.create_from_session()`](apps/app_operation/models/proxies/op_purchase.py:180) — `INDIVIDUAL` templates create one `InventoryMovementLine` (qty `1`) per head, each lazy-creating a tagged `Product`.
- [`InventoryMovementLine.save()`](apps/app_inventory/models.py:1202) — when `product_id is None`, delegates to [`InvoiceItem.create_products_for_item()`](apps/app_inventory/models.py:454), which for `INDIVIDUAL` creates one `Product` (qty 1, unique tag) per head.
- [`register_deferred_movements()`](apps/app_inventory/views.py:1023) — same one-line-per-head (qty 1) pattern.
- Existing test [`test_create_from_session_with_received_qty()`](apps/app_operation/tests/operations/purchase/test_purchase_create.py:548) — `received_qty=10` → 10 lines (qty 1) → 10 tagged products.

## Symptom (reported)

> "I created a purchase operation of ID 3; when I register a new movement, no new product line created."

## Root cause

The operation detail page's **Record Movement** button links to
[`create_purchase_movement`](apps/app_inventory/urls.py:57) →
[`_create_inventory_movement()`](apps/app_inventory/views.py:663). That shared
view derived every line's product from the invoice item's **first linked
product**:

```python
if not line.product_id:
    first_product = line.invoice_item.products.first()
    ...
    line.product = first_product
```

Because `line.product_id` was set **before** `save()`, the lazy-creation branch in
`InventoryMovementLine.save()` (`if is_new and self.product_id is None ...`)
never fired for `INDIVIDUAL` templates. Every new movement line reused the same
first product, so **no new product line was created**. (If the item had no linked
product at all, the view errored with "Invoice item has no linked product".)

## Fix

[`apps/app_inventory/views.py`](apps/app_inventory/views.py:733) — in
`_create_inventory_movement()`, for **PURCHASE + INDIVIDUAL** tracking, expand
each submitted line into **one `InventoryMovementLine` per head (qty `1`) with
`product=None`**, so `InventoryMovementLine.save()` lazy-creates a new tagged
`Product` per line — matching `create_from_session()` /
`register_deferred_movements()`.

For **COMMODITY** purchases and **all SALE** movements the previous
"derive from first linked product" behavior is preserved (SALE must reference an
existing product; COMMODITY is one bulk line).

The success message now reports the actual number of lines created.

## Tests

- Updated [`test_create_inventory_movement_purchase()`](apps/app_inventory/tests/test_inventory_movement.py:59) to assert the contract: receiving qty 3 → 3 lines (qty 1), 3 tagged products, each ACTIVE with stock state 1.
- Added [`test_purchase_movement_creates_new_product_per_animal()`](apps/app_inventory/tests/test_inventory_movement.py:113) — the regression: purchase with 4 heads already received, then receiving the remaining 6 via the movement form must yield **10 lines and 10 tagged products** (not reuse the first product).

## Implementation log

Implemented on 2026-08-12 (code mode):

- `apps/app_inventory/views.py` — `_create_inventory_movement()` now expands
  PURCHASE+INDIVIDUAL rows into one qty-1 line per head with `product=None`
  (lazy product creation), preserving first-product derivation for
  COMMODITY/SALE. Also fixed the shadowing of the gettext `_` import (loop
  variable renamed `head_idx`).
- `apps/app_inventory/tests/test_inventory_movement.py` — updated
  `test_create_inventory_movement_purchase` and added
  `test_purchase_movement_creates_new_product_per_animal`.

Verification:
- `python manage.py check` → no issues.
- `manage.py test apps.app_inventory.tests.test_inventory_movement` → 22 tests OK.
- `manage.py test --parallel=10 --keepdb apps.app_inventory
  apps.app_operation.tests.operations.purchase apps.app_operation.tests.operations.sale
  apps.app_operation.tests.views.test_views_get_operation_detail_view` → 304 tests OK.
