# Plan: Operation Still Shows "Received" After Reversing a Movement Line

**Status:** Implemented — see Implementation log below.
**Source of truth:** verified against the real code in `apps/app_inventory` and
`apps/app_operation`.

---

## Symptom (reported)

1. Created a PURCHASE operation.
2. Received the purchased items as **multiple** `InventoryMovementLine` rows.
3. Reversed **one** of those movement lines.
4. After the reversal, the **operation detail page still shows the items as
   received** (full quantity), even though the stock state itself is correct.

---

## Root cause

Reversing a [`InventoryMovementLine`](apps/app_inventory/models.py:1221) creates
a **new reversal row** pointing back to the original via `reversal_of` (reverse
relation `reversed_by`). The original row is left in place — nothing is deleted.

The stock layer already treats a reversed original as physically inactive:

- [`active_movements()`](apps/app_inventory/stock.py:31) and
  [`_item_moved_qty()`](apps/app_inventory/stock.py:137) compute the set of
  "reversed originals" and exclude both the reversal row **and** the reversed
  original.

But the **operation-detail / movement-form quantity computations** only filter
`reversal_of__isnull=True` and therefore **still count the reversed original** as
moved. This makes the UI show a stale "received" quantity and blocks re-receiving
the reversed amount.

### The canonical "wrong" pattern

```python
InventoryMovementLine.objects.filter(
    invoice_item=item,
    reversal_of__isnull=True,          # OK — skips reversal rows
    # MISSING: .exclude(id__in=<reversed originals>) — counts them anyway
)
```

### Affected call sites (production code)

1. **`Operation.get_items_data()`** — [`apps/app_operation/models/operation.py:748`](apps/app_operation/models/operation.py:748)
   - `moved_qty` (the "Received / Delivered" figure), `remaining_qty`,
     `is_fully_moved`, and the `movement_lines` queryset (the "Movements(n)"
     count).
   - Drives both the operation-detail status card
     ([`inventory_movement_status.html`](apps/app_operation/templates/app_operation/snippets/detail/inventory_movement_status.html))
     and the invoice-items list
     ([`invoice_items_list.html`](apps/app_operation/templates/app_operation/invoice_items_list.html))
     via [`operation_detail_view()`](apps/app_operation/views/detail.py:75) and
     [`invoice_items_list_view()`](apps/app_operation/views/invoice_items.py:106).
   - **This is the direct cause of the reported symptom.**

2. **`InvoiceItem.build_movement_json()`** — [`apps/app_inventory/models.py:500`](apps/app_inventory/models.py:500)
   - `already_moved` / `max_allowed` for the movement form's client-side budget.

3. **`InventoryMovementLine.clean()` over-delivery guard** — [`apps/app_inventory/models.py:1099`](apps/app_inventory/models.py:1099)
   - Sums reversed originals into `already_moved`, so after a reversal the guard
     wrongly reports the item as fully moved and **blocks re-receiving** the
     reversed quantity.

4. **`register_deferred_movements()`** — [`apps/app_inventory/views.py:954`](apps/app_inventory/views.py:954)
   - `already_moved` / `remaining` for the deferred-receipt flow, same effect.

---

## Fix

Add one shared helper to the stock module (the designated "single source of truth"
for stock queries) that returns the **active, non-reversed movement lines for an
invoice item**, mirroring `active_movements()` but keyed on `invoice_item`:

```python
# apps/app_inventory/stock.py
def active_lines_for_item(item):
    """Non-reversal movement lines for an invoice item, excluding the
    originals that have been reversed (mirrors active_movements())."""
    from apps.app_inventory.models import InventoryMovementLine

    reversed_originals = InventoryMovementLine.objects.filter(
        invoice_item=item, reversal_of__isnull=False
    ).values_list("reversal_of_id", flat=True)
    return (
        InventoryMovementLine.objects.filter(
            invoice_item=item, reversal_of__isnull=True
        )
        .exclude(id__in=list(reversed_originals))
        .select_related("operation")
    )
```

Then use it (or the equivalent `exclude` of reversed originals) in each call site:

### 1. `Operation.get_items_data()` — the main fix
- Compute the item's `reversed_originals` and build the active queryset (as in the
  helper above).
- `moved_qty = Sum(active_lines)`; `remaining_qty = adjusted_quantity - moved_qty`;
  `is_fully_moved` follows automatically.
- `movement_lines` should be the **active** queryset so the "Movements(n)" count
  matches the rows shown as active.
- Keep the existing sign convention (plain sum of quantities) — do **not** switch
  to the direction-aware `movement_delta` here, to avoid changing SALE display
  semantics in this bug-fix pass.

### 2. `InvoiceItem.build_movement_json()`
- Extend `already_filter` to also exclude the operation's reversed-original ids:
  `& ~Q(movement_lines__id__in=<reversed_originals>)`, where `reversed_originals`
  is collected once from
  `InventoryMovementLine.objects.filter(invoice_item__operation=operation,
  reversal_of__isnull=False)`.

### 3. `InventoryMovementLine.clean()` over-delivery guard
- Exclude reversed originals from `already_moved_qs` before summing.

### 4. `register_deferred_movements()`
- Exclude reversed originals from the `already_moved` aggregation.

---

## Tests

Add regression tests (extend existing suites; no schema change so reuse-db is fine):

- **`apps/app_inventory/tests/test_inventory_movement.py`** — new test:
  1. PURCHASE → receive 3 separate lines (e.g. qty 4 + 4 + 2 of 10).
  2. Reverse the middle line via `line.reverse(officer=...)`.
  3. Assert:
     - `operation.get_items_data()[i]["moved_qty"]` == active net (8),
       not the raw 10.
     - `remaining_qty` reflects the reversed amount (2 → can re-receive).
     - `is_fully_moved` is `False` (not "Complete").
     - `InvoiceItem.build_movement_json(operation)` reports
       `already_moved` == 8 and `max_allowed` == 2.
     - A new `InventoryMovementLine.full_clean()` re-receiving 2 succeeds
       (guard does not over-count), and re-receiving 3 is rejected.

- **`apps/app_operation/tests/views/test_views_get_operation_detail_view.py`** —
  assert the detail page context `items_data` shows the reduced `moved_qty`
  after a movement-line reversal.

- **Deferred receipt flow** — cover `register_deferred_movements` re-receiving
  after a reversal (extend `apps/app_inventory/tests/test_inventory_movement.py`
  or the deferred-movement test module if one exists).

---

## Verification

```bash
pytest -q apps/app_inventory/tests/test_inventory_movement.py \
       apps/app_operation/tests/views/test_views_get_operation_detail_view.py
python manage.py check
pytest -q apps/app_inventory apps/app_operation/tests/operations/purchase  # broader
```

---

## Out of scope / notes

- The reversal mechanics and stock-state math (`movement_state`, `Product.status`)
  are **correct** — no change needed there.
- `apps/app_inventory/models.py:499` (`is_physically_moved`) and the operation
  `reverse()` internals that iterate `reversal_of__isnull=True` to find *originals*
  to reverse are intentional and should stay as-is.
- Optional consistency check (flag for review, not required for the symptom):
  `Operation.reverse()`'s "was the product moved" probe at
  [`apps/app_operation/models/operation.py:1062`](apps/app_operation/models/operation.py:1062)
  still counts an individually-reversed line as "moved"; low-risk edge case.

---

## Implementation log

Implemented on 2026-08-12 (code mode):

- Added `active_lines_for_item(item)` to `apps/app_inventory/stock.py` — returns
  the invoice item's active (non-reversal, non-reversed-original) movement lines,
  mirroring `active_movements()`.
- `apps/app_operation/models/operation.py` — `get_items_data()` now computes
  `moved_qty`/`remaining_qty`/`is_fully_moved`/`movement_lines` from
  `active_lines_for_item(item)` so reversed originals no longer count as
  received/delivered. Fixes the operation detail + invoice-items list display.
- `apps/app_inventory/models.py` — `InvoiceItem.build_movement_json()` excludes
  reversed originals from `already_moved`/`max_allowed`; `InventoryMovementLine.clean()`
  over-delivery guard excludes reversed originals from `already_moved_qs`.
- `apps/app_inventory/views.py` — `register_deferred_movements()` excludes
  reversed originals from `already_moved` (remaining qty).
- Tests: added `test_get_items_data_excludes_reversed_movement_lines` and
  `test_operation_detail_shows_reduced_moved_qty_after_reversal` to
  `apps/app_inventory/tests/test_inventory_movement.py`.

Verification:
- `python manage.py check` → no issues.
- `manage.py test apps.app_inventory.tests.test_inventory_movement` → 21 tests OK
  (incl. the 2 new ones).
- `manage.py test --parallel=10 --keepdb apps.app_inventory
  apps.app_operation.tests.operations.purchase apps.app_operation.tests.operations.sale
  apps.app_operation.tests.views.test_views_get_operation_detail_view` → 303 tests OK.
- `manage.py test --parallel=10 --keepdb apps.app_operation apps.app_adjustment`
  → 1118 tests OK.
