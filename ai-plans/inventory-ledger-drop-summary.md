# Resume — Inventory simplification: ledger dropped (Phase B complete)

**Purpose:** A self-contained summary so work can be resumed from a fresh task without re-reading the
whole conversation. Companion to `inventory-app-simplification-analysis.md` and
`inventory-phase-a-plan.md`.

**Status (2026-08-12):** Phases A and B are **implemented and verified — full suite green
(1435 tests OK via `manage.py test --parallel=8`)**. `python manage.py check` and
`makemigrations --check` both pass (no pending migrations).

---

## 1. The project direction (why we are here)

The user flagged the inventory app as over-engineered. Its root cause: **a single `Product` model
serves animals, medicine, feed and general commodities**. The agreed simplification:

1. **Phase A (done)** — move `MedicalRecord` to a new `app_animal` app; reconcile valuation to one
   method; decouple `Product.status` from linked operations (movement/presence-based).
2. **Phase B (done)** — **drop the `ProductLedgerEntry` table** entirely; stock is computed from
   `InventoryMovementLine` + `InvoiceItem` via a new `apps/app_inventory/stock.py` module.
3. **Still deferred (future)** — remove `Product.entity` (ownership from movements); split into
   `Animal` / `Commodity` models.

---

## 2. Current state — what is implemented

### 2.1 `apps/app_inventory/stock.py` (NEW — the single source of truth)

Replaces every `ProductLedgerEntry` query. API:

- `movement_state(product, as_of=None)` → `{"quantity", "value"}` — direction-aware net movement
  (PURCHASE/BIRTH `+`, DEATH/CONSUMPTION `−`, SALE `−` for seller dispatch / `+` for buyer receipt)
  × carried cost (`product.unit_price`) + active capital gain/loss. Reversal-aware (reversal lines
  and their reversed originals are excluded).
- `portfolio(entity, as_of=None)` → list of `{product_id, quantity(>0), value}` (ownership-based).
- `inventory_value(entity, as_of=None)` → `Decimal` sum of per-product movement states.
- `pending_items(entity=None, as_of=None)` → issued − moved per `InvoiceItem` (positive = inbound
  pending, negative = outbound pending).
- `pending_deliveries(entity=None, as_of=None)` → alias filtered to positive pending.
- `capital_delta(product)` → value-only capital gain/loss from **non-reversed** CAPITAL_GAIN/LOSS
  operations (the `operation__reversed_by__isnull=True` filter preserves create+reverse invariants).

### 2.2 Model changes (`apps/app_inventory/models.py`)

- `ProductLedgerEntry` class **removed**.
- `Product.current_value` → `movement_state(self, as_of=today)["value"]` for physically-moved
  products (nominal `unit_price × quantity` for unmoved ones).
- `InventoryMovementLine._validate_availability` → uses `stock.movement_state`.
- `InventoryMovementLine.save()` no longer writes ledger rows.
- `InventoryMovementLine.reverse()` → reversal line only; stock queries exclude reversals.

### 2.3 Call sites rewired to the stock module

- `apps/app_operation/models/proxies/op_sale.py` — `create_from_session` availability via
  `movement_state`; no `record()`.
- `apps/app_operation/models/proxies/op_purchase.py` — no `record()`.
- `apps/app_operation/views/create_operation/sale_wizard.py` — `stock_portfolio` +
  `movement_state` (import aliased because a local var named `portfolio` shadows the function).
- `apps/app_operation/views/create_operation/evaluation.py` — no `record()`.
- `apps/app_operation/forms.py` (`SaleItemForm.clean`) — `movement_state`.
- `apps/app_inventory/views.py` — `stock_detail`, `stock_history`, `quick_consume`,
  `product_detail` (the last one previously prefetched `ledger_entries` — a runtime bug now fixed).
- `apps/app_operation/models/period.py` — `inventory_value_previous/end/value` via
  `stock.inventory_value`.
- `apps/app_entity/views/entity_detail.py` — `inventory_value`.
- `apps/app_adjustment/models.py` — `InvoiceItemAdjustment.reverse()` and
  `InvoiceItemAdjustmentLine.save()` no longer call `record_adjustment_line`.

### 2.4 Removed

- `apps/app_inventory/management/commands/backfill_product_ledger.py` (deleted).
- `apps/app_inventory/tests/test_product_ledger_entry.py` (deleted; replaced by
  `test_stock.py`).

### 2.5 Migration

- `apps/app_inventory/migrations/0014_remove_productledgerentry_*.py` — removes indexes and
  `DeleteModel(ProductLedgerEntry)`.

### 2.6 Tests

- `apps/app_inventory/tests/test_stock.py` (NEW) — movement_state / portfolio / inventory_value /
  pending_items scenarios (incl. direction-aware sale, reversal exclusion, written-off netting).
- All ledger-asserting tests rewritten to assert movement lines / stock state while **keeping the
  coverage-manifest method names** (so `CoverageManifestTest` passes):
  - `test_inventory_movement.py`, `test_quick_consume_from_stock.py`, `test_product.py`
    (`_make_valued_product` now uses real capital operations).
  - birth/death/consumption create + reversal tests.
  - purchase create (`test_create_from_session_ledger_entries_created` now checks obligation /
    movement lines), sale create-from-session.
  - adjustment tests (`test_invoice_item_adjustment_ledger_entry.py` now asserts line deltas;
    reversal/validation tests assert effective-amount restoration).
  - `apps/app_entity/tests/test_views_get_entity_detail_view.py` — movement-based stock value.
- `apps/app_operation/tests/base.py` — removed unused `assert_ledger`; `_ledger_totals()` is now
  movement-based (keeps the create+reverse "world unchanged" differential checks working).

### 2.7 Prior work — internal-entity purchase/sale fix (rev 4, implemented earlier)

Strategy (user): **block PURCHASE between internal entities; allow SALE as the intra-farm
stock-transfer mechanism.** An internal entity = `Entity.is_internal == True` (SYSTEM forced
internal, WORLD forced non-internal). Full detail: `ai-plans/internal-entity-transfer-stock-plan.md`
(rev 4) and `ai-plans/fix-sale-mechanism-plan.md`.

- **PURCHASE blocking (double-count fix):** internal entities are excluded from
  `PurchaseOperation.get_related_entities()` and the `PurchaseWizardStep1Form` vendor queryset;
  `clean_destination()` rejects internal vendors ("Internal entities cannot be vendors…").
  Purchases become external-only, removing the vendor-side double-count.
- **SALE buyer receipt (transfer):** `SaleOperation.create_from_session()` — when
  `client.is_internal`, the buyer receives an **ACTIVE product** (carried `unit_price` = the sale
  price) plus an inbound receipt movement, so the goods appear in the client's live stock.
  External-client sales are unchanged (no buyer copy).
- **Direction-aware `Product.status`:** receiver side → `ACTIVE`; disposer side →
  `SOLD`/`DEAD`/`CONSUMED` (op-type mapping as fallback; external flows unchanged).
- **Direction-aware movement recording:** on a SALE, a source-owned product (the internal client's
  receipt) records an inbound `+` movement; a destination-owned product (the seller's dispatch)
  records outbound `−`.
- **Buyer visibility:** `stock_detail` classifies a SALE movement by ownership (source-owned →
  incoming); `portfolio`/`portfolio_as_of` match by `product__entity`; `_outbound_owner_entity`
  treats the buyer receipt as inbound; `build_movement_json` and the over-delivery guard count per
  owner.
- **Sale wizard (earlier fix):** the wizard now selects from the seller's **existing products**
  (`sale_select_product_view`), `SaleItemForm` re-validates ownership/availability against the
  selected product, and `create_from_session` **affects the existing product** (no minting/clone).
  The old generic sale create path was removed.
- **Tests:** purchase-blocking, internal-client-receives-active-product, external-client-no-copy,
  buyer-in-stock, receipt-reversal, and direction-aware status.

---

## 3. Known behavior notes / caveats

- **Item adjustments no longer write value-only inventory rows.** An
  `InvoiceItemAdjustmentLine` still computes exact `quantity_delta` / `value_delta` (tested), but
  those deltas are **not** reflected in `stock.movement_state` valuation (which is
  quantity × carried cost + capital). This is a deliberate simplification; revisit if adjusted
  purchase prices must change on-hand value.


---

## 4. Verification commands

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test --parallel=8        # full suite (≈ 4.5 min)
# targeted:
.venv/bin/python manage.py test --parallel=8 \
  apps.app_inventory.tests.test_stock \
  apps.app_inventory.tests.test_inventory_movement \
  apps.app_inventory.tests.test_quick_consume_from_stock \
  apps.app_inventory.tests.test_product \
  apps.app_operation.tests.operations.inventory \
  apps.app_adjustment.tests
```

### 4.1 Deep check output (`manage.py check --deploy`)

`manage.py check` (dev) prints: **System check identified no issues (0 silenced).**

`manage.py check --deploy` prints **7 security warnings** (0 silenced) — deployment-hardening
only, **not introduced by this work**:

```text
?: (security.W004) SECURE_HSTS_SECONDS not set
?: (security.W008) SECURE_SSL_REDIRECT not set to True
?: (security.W009) SECRET_KEY < 50 chars / auto-generated (django-insecure- prefix)
?: (security.W012) SESSION_COOKIE_SECURE not set to True
?: (security.W016) CSRF_COOKIE_SECURE not set to True
?: (security.W018) DEBUG=True in deployment
?: (security.W020) ALLOWED_HOSTS must not be empty in deployment
System check identified 7 issues (0 silenced).
```

---

## 5. Next steps (deferred, not started)

1. **Remove `Product.entity`** — derive ownership purely from movement lines (the user's original
   suggestion: a product is created once by Birth/Purchase from a non-internal entity, then tracked
   by movements). Requires: stock queries / `portfolio` / `_outbound_owner_entity` /
   `stock_detail` SQL and the sale buyer-copy flow to switch from `Product.entity` to movement-based
   ownership; update ownership tests and the sale wizard's "select from existing products".

  User: This will be a huge migration. don't do.


2. **Split `Product` into `Animal` / `Commodity`** — the deep fix for the single-model problem;
   `app_animal` already exists as the future home of `Animal` (`MedicalRecord` FK to
   `app_inventory.Product` stays until the split).use
    
    User: This will be a huge migration. don't do.

3. Re-verify the internal-entity transfer story (SALE as the transfer mechanism, PURCHASE blocked
   for internal vendors) after the ownership refactor — see
   `internal-entity-transfer-stock-plan.md` (rev 4).

---

## 6. Key files map

| Concern | File |
|---|---|
| Stock queries (new) | `apps/app_inventory/stock.py` |
| Inventory models | `apps/app_inventory/models.py` |
| Operation save/reverse | `apps/app_operation/models/operation.py` |
| Sale / purchase proxies | `apps/app_operation/models/proxies/op_sale.py`, `op_purchase.py` |
| Sale wizard | `apps/app_operation/views/create_operation/sale_wizard.py` |
| Stock views | `apps/app_inventory/views.py` |
| Period inventory value | `apps/app_operation/models/period.py` |
| Adjustment models | `apps/app_adjustment/models.py` |
| Migration (drop table) | `apps/app_inventory/migrations/0014_remove_productledgerentry_*.py` |
| Test helpers | `apps/app_operation/tests/base.py` |
| Phase A + B plan record | `ai-plans/inventory-phase-a-plan.md` (sections 6 & 7) |

---

## 7. Post-B update — split `create_inventory_movement` + fix receive-after-sale (2026-08-12)

**Bug:** a single generic `create_inventory_movement` served both PURCHASE (receive) and SALE
(dispatch). Receiving the remaining purchase qty was blocked with
`Product 'BAM1' has status SOLD and cannot be used in new operations.` when the lot had been
partially sold: the movement-line `clean()` only allowed a terminal status that matched the
**current operation's** type, so an inbound receipt onto an already-SOLD lot failed.

**Fix — implemented and verified (`apps.app_inventory` + purchase/sale/inventory/period suites,
437 tests OK; `manage.py check` clean):**

1. `apps/app_inventory/models.py` — `InventoryMovementLine.clean()`: inbound operations
   (PURCHASE/BIRTH) always allow the movement regardless of the lot's own status. The purchase
   created the `Product` instance; receiving the rest simply re-stocks it (over-delivery is still
   capped by the invoice-item quantity check).
2. `apps/app_inventory/views.py` — split the view into two isolated flows:
   - `create_purchase_movement` (PURCHASE only — receive),
   - `create_sale_movement` (SALE only — dispatch),
   both delegating to the shared `_create_inventory_movement(request, operation_pk, expected_type)`.
   A backwards-compatible `create_inventory_movement` dispatcher (redirect) is retained for the old URL.
3. `apps/app_inventory/urls.py` — new routes
   `operations/<pk>/movement/create/purchase/` (`create_purchase_movement`) and
   `operations/<pk>/movement/create/sale/` (`create_sale_movement`); old route kept as the dispatcher.
4. Templates updated to the type-specific URLs (branch on `operation.operation_type`):
   `inventory_movement_status.html`, `invoice_items_list.html`, `stock_history.html`.
   `stock.py::pending_items()` now returns `operation__operation_type` so the stock-history rows gate
   the "Create Movement" button to PURCHASE (inbound) / SALE (outbound) only.
5. Tests: existing movement tests moved to the new URL names; added
   `test_purchase_receive_remaining_after_partial_sale` (receive 1 → sell 1 → receive 9) and
   `test_sale_movement_rejects_operation_mismatch`; closed-period guard test now posts to
   `create_purchase_movement`.
