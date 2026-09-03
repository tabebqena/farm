# Stock — Movement-Based Inventory Contract

<!--
Adapted from docs/specs/operations/_OPERATION_SPEC_TEMPLATE.md for the inventory
subsystem. Stock is NOT an operation — it is the movement-derived physical layer
that Purchase / Sale / Birth / Death / Consumption write to. Where the operation
template documents money flow and settlement, this document documents the
**physical flow** (quantity + carried value) and the **movement-based stock
state**.

How this spec is kept true:
  1. The query module (apps/app_inventory/stock.py) is the single source of
     truth for "what's on hand" — every clause in §4 is registered to it.
  2. The physical event is InventoryMovementLine — every clause in §5 registers
     to its model/clean/save/reverse and to the movement views.
  3. Read the tests (test_stock.py, test_inventory_movement.py,
     test_quick_consume_from_stock.py, view tests) and map every branch to a
     pinning test (§10).
  4. Where code and spec disagree, fix the code, not the spec.
-->

**Epic:** 3 — Inventory & Invoice System
**Type:** subsystem — movement-derived physical inventory, no separate ledger table
**Actions:** `receive`, `dispatch`, `write off` (auto), `consume` (quick), `reverse movement`, `query` (state / portfolio / value / pending)
**Contract status:** v1 (new) — movement-based stock contract; branches recorded, implementing code registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Stock** subsystem.
> Every clause below is registered to its implementing code (query module → model → movement line → view) and to its pinning test.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> See [`_OPERATION_SPEC_TEMPLATE.md`](../operations/_OPERATION_SPEC_TEMPLATE.md) for the shared structure and
> [`op_13_purchase.md`](../operations/op_13_purchase.md) / [`op_14_sale.md`](../operations/op_14_sale.md) /
> [`op_17_birth.md`](../operations/op_17_birth.md) / [`op_18_death.md`](../operations/op_18_death.md) /
> [`op_19_consumption.md`](../operations/op_19_consumption.md) /
> [`capital_valuation_operation.md`](../operations/op_20_capital_valuation_operation.md) for the operations that drive stock (movement lines and value).

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Subsystem | Stock — physical inventory (quantity + carried value) | |
| Operation types that write it | `PURCHASE`, `BIRTH` (inbound) · `SALE` (bidirectional) · `DEATH`, `CONSUMPTION` (outbound) · value-only `CAPITAL_GAIN` / `CAPITAL_LOSS` (no movement line — see §4) | [`OperationType`](../../../apps/app_operation/models/operation_type.py) |
| Query module (single source of truth) | [`stock.py`](../../../apps/app_inventory/stock.py) | |
| Core model (the physical event) | `InventoryMovementLine` | [`models.py`](../../../apps/app_inventory/models.py:966) |
| Supporting models | `Product`, `InvoiceItem`, `ProductTemplate`, `ProductCapitalValuation` | [`models.py`](../../../apps/app_inventory/models.py:538) |
| URL slug | `stock_detail` → `entity/<entity_pk>/stock/` | [`urls.py`](../../../apps/app_inventory/urls.py:8) |
| Registered in | `urlpatterns` (`app_inventory.urls`) | [`urls.py`](../../../apps/app_inventory/urls.py:8) |
| Cross-op reference | rows PU / SA / BI / DE / CO / CG / CL | [`operations-comparison.md`](../operations/operations-comparison.md:100) |

**Configuration flags (product template & query layer):**

| Flag | Value | Meaning |
|------|-------|---------|
| `tracking_mode` | `INDIVIDUAL` (ANIMAL) / `COMMODITY` (FEED/MEDICINE/PRODUCT) | one `Product` per head (tagged) vs one bulk `Product` carrying the full quantity |
| `nature` | `ANIMAL` / `FEED` / `MEDICINE` / `PRODUCT` | drives `_ALLOWED_OP_TYPES`, `tracking_mode`, `can_die`/`can_be_consumed` |
| `_ALLOWED_OP_TYPES` | per nature frozenset | which operation types the template accepts (e.g. ANIMAL can never be consumed) |
| `_INBOUND_TYPES` | `(PURCHASE, BIRTH)` | movement sign + (`+)` in `movement_delta` |
| `_OUTBOUND_TYPES` | `(DEATH, CONSUMPTION)` | movement sign − in `movement_delta` |
| `_ISSUE_SIGN` | `+1` inbound, `-1` outbound (SALE `-1`) | issued-quantity sign for pending/obligation maths |
| `can_die` / `can_be_consumed` | bool | flag-level gating on top of the nature allow-list |
| `minimum_quantity` | `1` Head / `0.01` Kg | unit increment enforced on invoice + movement quantities |
| `valuation_unit_cost` | `product.unit_price` (else `0.00`) | the carried purchase-price basis used to value movements |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements the stock subsystem**. The spec is the primary source of contract; each row links the clause to the code that must honor it.

### 2.1 Query layer (`apps/app_inventory/stock.py`)

| Concern | Implementing code |
|---------|-------------------|
| Carried unit cost for valuation | `valuation_unit_cost` |
| Active (non-reversed) movement lines, per product / per item | `active_movements` / `active_lines_for_item` |
| Direction-aware signed quantity of one line | `movement_delta` |
| Value-only capital gain/loss (active, non-reversed) | `capital_delta` |
| On-hand `{"quantity", "value"}` as of a date | `movement_state` |
| Per-entity physical presence (positive qty only) | `portfolio` |
| Net book value of an entity's inventory | `inventory_value` |
| Direction-aware moved qty for an invoice item | `_item_moved_qty` |
| Inbound / outbound contract obligations | `pending_items` / `pending_deliveries` |

### 2.2 Model layer (`apps/app_inventory/models.py`)

| Concern | Implementing code |
|---------|-------------------|
| Template config: nature → tracking mode, allowed ops, tags, min qty | `ProductTemplate` |
| Template accepts an operation type (nature + flag gating) | `ProductTemplate.accepts_operation` |
| Next unique animal tag (never collides via `all_objects`) | `ProductTemplate.next_tag` |
| Invoice item clean: op-type compatibility + unit increment | `InvoiceItem.clean` |
| Adjustment-aware item quantities/prices (active, non-reversed) | `InvoiceItem.adjusted_quantity` / `adjusted_unit_price` |
| Product creation per tracking mode (one-per-head vs bulk) | `InvoiceItem.create_products_for_item` |
| Movement-form budget (already moved / max allowed, reversal-aware) | `InvoiceItem.build_movement_json` |
| Value-only capital valuation row (gain/loss — no movement line) | `ProductCapitalValuation` |
| Physical status derived from active movement lines | `Product.status` |
| Obligated-only vs physically-moved classification | `Product.is_physically_moved` / `is_obligated_only` |
| Status/eligibility gate for downstream operations | `Product.validate_active` |
| Movement-based book value | `Product.current_value` |
| Concurrency: row locks during availability checks | `Product.lock_ids` |
| Physical event: immutability, availability, ownership, unit, lazy product | `InventoryMovementLine` |
| Reversal of a physical event | `InventoryMovementLine.reverse` / `batch_reverse` |

### 2.3 Operations that write stock (cross-cutting)

| Concern | Implementing code |
|---------|-------------------|
| Operation `inventory_owner_entity` / `inventory_receiving_entity` | `InventoryOperationMixin` (inherited by the lean `Operation` base, app_operation) |
| Auto movement on create (Birth/Death/Consumption) | `InventoryOperationMixin.save_inventory` → [`_auto_create_inventory_movements`](../../../apps/app_operation/models/operation.py) |
| Wizard Purchase/Sale movements | `create_from_session` (Purchase / Sale) |
| Reversal dependency guard (outbound ops with later moves) | `InventoryOperationMixin._validate_reversal_inventory_guards` (called by `Operation.reverse`) |
| Shared stock-event config (no payments / no category / no repayment / invoice-driven) | `StockEventMixin` (Birth / Death / Consumption / Capital) |

### 2.4 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Stock detail (physically present cards, search, pagination) | [`stock_detail`](../../../apps/app_inventory/views.py:25) |
| Stock history (movement list, IN/OUT filters, pending) | [`stock_history`](../../../apps/app_inventory/views.py:173) |
| Product detail (physical presence via `movement_state`) | [`product_detail`](../../../apps/app_inventory/views.py:454) |
| One-step consume from stock | [`quick_consume`](../../../apps/app_inventory/views.py:318) |
| Receive (PURCHASE movement form) | [`create_purchase_movement`](../../../apps/app_inventory/views.py:615) |
| Dispatch (SALE movement form) | [`create_sale_movement`](../../../apps/app_inventory/views.py:630) |
| Deferred movement registration | [`register_deferred_movements`](../../../apps/app_inventory/views.py:938) |
| Reverse a movement line / batch reverse | [`reverse_inventory_movement_line`](../../../apps/app_inventory/views.py:847) / [`batch_reverse_inventory_movement_lines`](../../../apps/app_inventory/views.py:887) |
| URLs | [`urls.py`](../../../apps/app_inventory/urls.py) |
| Templates | `stock_detail.html`, `stock_history.html`, `product_detail.html`, `inventory_movement_form.html`, `deferred_movement_form.html`, `reverse_movement*_confirm.html` |

### 2.5 Tests

| Concern | Test file |
|---------|-----------|
| `movement_state` / `portfolio` / `inventory_value` / `pending_items` branches | [`test_stock.py`](../../../apps/app_inventory/tests/test_stock.py) |
| Movement create/receive/dispatch/reversal/model guards | [`test_inventory_movement.py`](../../../apps/app_inventory/tests/test_inventory_movement.py) |
| Quick-consume view pipeline + guards | [`test_quick_consume_from_stock.py`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py) |
| Stock detail view | [`test_views_get_stock_detail_view.py`](../../../apps/app_inventory/tests/test_views_get_stock_detail_view.py) |
| Stock history view | [`test_views_get_stock_history_view.py`](../../../apps/app_inventory/tests/test_views_get_stock_history_view.py) |
| Product valuation / current_value | [`test_product.py`](../../../apps/app_inventory/tests/test_product.py) |
| Reverse / batch-reverse / deferred / backward-compat view actions | [`test_views_movement_actions.py`](../../../apps/app_inventory/tests/test_views_movement_actions.py) |

---

## 3. Physical flow & entities

- **Stock keeper (owner):** a **Project** entity. Every `Product` carries `entity` (the project whose inventory it belongs to).
- **Inbound (receipt):**
  - `PURCHASE` — the buying project receives from a vendor (movement sign +).
  - `BIRTH` — the project receives newborns (movement sign +).
  - `SALE` — when the product is owned by the SALE **source** (an internal-client receipt), the buyer's copy gains (+) stock.
- **Outbound (dispatch / write-off):**
  - `SALE` — when the product is owned by the SALE **destination** (the seller), the seller's copy loses (−) stock.
  - `DEATH` — the project writes livestock off to the System (sign −).
  - `CONSUMPTION` — the project writes consumables off to the System (sign −).

**Movement flow:**

| # | Operation type | Direction for owner | `movement_delta` | Value basis |
|---|----------------|---------------------|------------------|-------------|
| 1 | `PURCHASE` | inbound | `+quantity` | carried cost (`product.unit_price`) |
| 2 | `BIRTH` | inbound | `+quantity` | carried cost |
| 3 | `SALE` (seller dispatch) | outbound | `-quantity` | carried cost |
| 4 | `SALE` (buyer receipt) | inbound | `+quantity` | carried cost |
| 5 | `DEATH` | outbound | `-quantity` | carried cost |
| 6 | `CONSUMPTION` | outbound | `-quantity` | carried cost |

> There is **no separate ledger table**. Every query is computed on demand from `InventoryMovementLine` (the physical events) plus `InvoiceItem` (contract obligations and capital value). This replaces the removed `ProductLedgerEntry` table.

---

## 4. Movement-based stock state

Derived from `movement_state(product, as_of)` — a dict `{"quantity", "value"}`:

```
quantity = Σ movement_delta(active lines as of as_of)          # net direction-aware
value    = quantity * valuation_unit_cost(product) + capital_delta(product)
```

> **Value-only writers.** `CAPITAL_GAIN` / `CAPITAL_LOSS` do **not** create movement lines — each records a `ProductCapitalValuation` row whose signed amount feeds `capital_delta` (quantity untouched, product stays `ACTIVE`). See [`capital_valuation_operation.md`](../operations/op_20_capital_valuation_operation.md).

| Function | Returns | Excludes |
|----------|---------|----------|
| `movement_state(product, as_of)` | `{"quantity", "value"}` on hand | reversal lines **and** the originals they reverse |
| `portfolio(entity, as_of)` | one row per product with `quantity > 0` | zero/negative-presence products |
| `inventory_value(entity, as_of)` | `Σ movement_state(...)["value"]` across owned products | — |
| `pending_items(entity, as_of)` | items where moved ≠ issued (`pending_qty` > 0 inbound, < 0 outbound) | items fully moved |

**Example invariant:** 100 kg @ $2 received, then 30 kg consumed → `movement_state == {"quantity": 70.00, "value": 140.00}` ([`test_stock.py`](../../../apps/app_inventory/tests/test_stock.py:109)).

---

## 5. Actions

### 5.1 `receive` (PURCHASE movement)

Entry points: movement form [`create_purchase_movement`](../../../apps/app_inventory/views.py:615) (POST `/operations/<pk>/movement/create/purchase/`), deferred registration, or the wizard (`create_from_session`). Converges on `InventoryMovementLine.save()`.

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| RC1 | Officer staff | `request.user.is_staff` | redirect + message | `"You must be an officer to create inventory movements."` | [`_create_inventory_movement`](../../../apps/app_inventory/views.py:672) | [`test_non_staff_cannot_create_movement`](../../../apps/app_inventory/tests/test_inventory_movement.py:183) |
| RC2 | Operation type is PURCHASE | `operation.operation_type == expected_type` | redirect + message | `"Inventory movements for this operation must use the PURCHASE flow."` | [`_create_inventory_movement`](../../../apps/app_inventory/views.py:687) | [`test_sale_movement_rejects_operation_mismatch`](../../../apps/app_inventory/tests/test_inventory_movement.py:686) |
| RC3 | Movement date not in a closed period | `not is_date_in_closed_period(operation.period_entity, date)` | `ValidationError` | `"Cannot record a movement dated within a closed financial period."` | [`_create_inventory_movement`](../../../apps/app_inventory/views.py:710) | covered by period suite |
| RC4 | Over-delivery guard | `already_moved + qty ≤ invoice_item.quantity` | `ValidationError` | `"Total moved quantity … would exceed the invoice item quantity."` | [`InventoryMovementLine.clean`](../../../apps/app_inventory/models.py:1131) | [`test_quantity_exceeds_invoice_item`](../../../apps/app_inventory/tests/test_inventory_movement.py:245) |
| RC5 | Unit consistency | `quantity % minimum_quantity == 0` | `ValidationError` | `"Quantity … must be a multiple of the minimum increment …"` | [`InventoryMovementLine.clean`](../../../apps/app_inventory/models.py:1167) | [`test_movement_rejects_quantity_not_multiple_of_minimum`](../../../apps/app_inventory/tests/test_inventory_movement.py:546) |
| RC6 | Item belongs to the operation | `invoice_item.operation == operation` | `ValidationError` | `"Invoice item does not belong to this operation."` | [`InventoryMovementLine.clean`](../../../apps/app_inventory/models.py:1103) | [`test_movement_rejects_invoice_item_from_other_operation`](../../../apps/app_inventory/tests/test_inventory_movement.py:907) |
| RC7 | Availability on receive | inbound receipts are **not** availability-gated | never fails | — | `_outbound_owner_entity()` returns `None` for inbound | — |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| RS1 | Movement line(s) created | `PURCHASE_MOVEMENT` physical event; `date`, `officer`, `notes`, `group_key` recorded | [`InventoryMovementLine.save`](../../../apps/app_inventory/models.py:1207) | [`test_create_inventory_movement_purchase`](../../../apps/app_inventory/tests/test_inventory_movement.py:59) |
| RS2 | INDIVIDUAL → one line per head | moving 10 animals → 10 lines of qty `1.00`, each lazily creating its own tagged `Product` (`ACTIVE`) | [`_create_inventory_movement`](../../../apps/app_inventory/views.py:751) + lazy save | [`test_purchase_movement_creates_new_product_per_animal`](../../../apps/app_inventory/tests/test_inventory_movement.py:120) |
| RS3 | COMMODITY → one line with full qty | moving 10 kg of corn → one line qty 10 | [`InventoryMovementLine.save`](../../../apps/app_inventory/models.py:1207) | [`test_purchase_commodity_receives_single_line_full_qty`](../../../apps/app_inventory/tests/test_inventory_movement.py:984) |
| RS4 | Product materialised ACTIVE | `movement_state(product)["quantity"] == received qty` | `movement_state` | [`test_create_inventory_movement_purchase`](../../../apps/app_inventory/tests/test_inventory_movement.py:112) |
| RS5 | Receive after partial sale allowed | inbound receipts are independent of the lot's status — receiving the rest re-activates a `SOLD` lot | [`InventoryMovementLine.clean`](../../../apps/app_inventory/models.py:1194) | [`test_purchase_receive_remaining_after_partial_sale`](../../../apps/app_inventory/tests/test_inventory_movement.py:595) |
| RS6 | Remaining qty decreases | `pending_qty` of the item moves toward 0 | `pending_items` / `build_movement_json` | [`test_get_items_data_excludes_reversed_movement_lines`](../../../apps/app_inventory/tests/test_inventory_movement.py:756) |

### 5.2 `dispatch` (SALE movement)

Entry points: [`create_sale_movement`](../../../apps/app_inventory/views.py:630) (POST `/operations/<pk>/movement/create/sale/`) or wizard. Same shared implementation as 5.1 with `expected_type = SALE`.

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| DC1 | Officer staff | `request.user.is_staff` | redirect + message | same as RC1 | [`_create_inventory_movement`](../../../apps/app_inventory/views.py:672) | shared with RC1 |
| DC2 | Operation type is SALE | `operation.operation_type == SALE` | redirect + message | `"…must use the SALE flow."` | [`_create_inventory_movement`](../../../apps/app_inventory/views.py:687) | [`test_sale_movement_rejects_operation_mismatch`](../../../apps/app_inventory/tests/test_inventory_movement.py:686) |
| DC3 | Movement date not in a closed period | as RC3 | `ValidationError` | same as RC3 | [`_create_inventory_movement`](../../../apps/app_inventory/views.py:710) | covered by period suite |
| DC4 | Ownership / location | moved product belongs to the seller (`operation.inventory_owner_entity`) | `ValidationError` | `"Product '…' does not belong to '…' and cannot be moved out of it."` | [`InventoryMovementLine.clean`](../../../apps/app_inventory/models.py:1155) | [`test_sale_movement_rejects_product_owned_by_another_entity`](../../../apps/app_inventory/tests/test_inventory_movement.py:310) |
| DC5 | Ownerless product rejected | `_outbound_owner_entity()` not `None` and product has an owner | `ValidationError` | same as DC4 | [`InventoryMovementLine.clean`](../../../apps/app_inventory/models.py:1155) | [`test_sale_movement_rejects_product_without_owner`](../../../apps/app_inventory/tests/test_inventory_movement.py:327) |
| DC6 | Availability | `qty ≤ movement_state(product, as_of=date)["quantity"]` | `ValidationError` | `"Insufficient stock: …"` | [`InventoryMovementLine._validate_availability`](../../../apps/app_inventory/models.py:1060) | [`test_sale_movement_rejects_qty_beyond_on_hand`](../../../apps/app_inventory/tests/test_inventory_movement.py:490) |
| DC7 | SALE-of-unreceived exemption | product not physically moved → availability skipped (sale records it) | never fails | — | [`_validate_availability`](../../../apps/app_inventory/models.py:1078) | [`test_sale_operation_movement`](../../../apps/app_inventory/tests/test_inventory_movement.py:203) |
| DC8 | Over-delivery / unit guards | same as RC4 / RC5 | `ValidationError` | — | [`InventoryMovementLine.clean`](../../../apps/app_inventory/models.py:1131) | shared with RC4 / RC5 |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| DS1 | Movement line created | `SALE_MOVEMENT` physical event | [`InventoryMovementLine.save`](../../../apps/app_inventory/models.py:1207) | [`test_sale_operation_movement`](../../../apps/app_inventory/tests/test_inventory_movement.py:203) |
| DS2 | Seller stock net − | `movement_state(seller_product)["quantity"]` decreases by dispatched qty | `movement_delta` | [`test_sale_dispatch_reduces_seller_stock`](../../../apps/app_inventory/tests/test_stock.py:147) |
| DS3 | Buyer receipt net + (internal client) | SALE source-owned product gains + on the buyer's copy | `movement_delta` | [`test_sale_buyer_receipt_increases_buyer_stock`](../../../apps/app_inventory/tests/test_stock.py:160) |
| DS4 | Product → `SOLD` | outbound dispatch drives the terminal status | `Product.status` | [`test_purchase_receive_remaining_after_partial_sale`](../../../apps/app_inventory/tests/test_inventory_movement.py:650) |
| DS5 | Pending outbound decreases | `pending_qty` of the item moves toward 0 | `pending_items` | [`test_pending_outbound_for_undelivered_sale`](../../../apps/app_inventory/tests/test_stock.py:355) |

### 5.3 `write off` (DEATH / CONSUMPTION — auto movement)

Movement lines are created automatically by the operation (`save_inventory` → `_auto_create_inventory_movements`), not by a standalone movement form. Availability is **always** enforced: you cannot write off more than the project physically holds.

#### 5.3.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| WC1 | Availability | `qty ≤ movement_state(product, as_of=date)["quantity"]` | `ValidationError` | `"Insufficient stock: …"` | [`_validate_availability`](../../../apps/app_inventory/models.py:1060) | [`test_death_movement_rejects_qty_beyond_on_hand`](../../../apps/app_inventory/tests/test_inventory_movement.py:497) / [`test_consumption_movement_rejects_qty_beyond_on_hand`](../../../apps/app_inventory/tests/test_inventory_movement.py:504) |
| WC2 | Equal-to-on-hand allowed | `qty == available` | passes | — | [`_validate_availability`](../../../apps/app_inventory/models.py:1060) | [`test_death_movement_accepts_qty_equal_to_on_hand`](../../../apps/app_inventory/tests/test_inventory_movement.py:523) |
| WC3 | Nature / flag gating | template `accepts_operation(DEATH|CONSUMPTION)` | op create fails | `"…cannot be used in a … operation."` | `InvoiceItem.clean` / `ProductTemplate.accepts_operation` | quick-consume suite (WC3 in §5.4) |

#### 5.3.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| WS1 | Auto movement line created | `DEATH_MOVEMENT` / `CONSUMPTION_MOVEMENT` | `Operation.save_inventory` → `_auto_create_inventory_movements` | inventory suite |
| WS2 | Product → `DEAD` / `CONSUMED` | terminal status from the outbound move | `Product.status` | [`test_quick_consume_creates_full_pipeline`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:107) |
| WS3 | Stock nets to zero (full write-off) | `movement_state["quantity"] == 0.00` | `movement_state` | [`test_portfolio_and_value_after_death_consumption_sale`](../../../apps/app_inventory/tests/test_stock.py:232) |

### 5.4 `consume` (quick, one-step view)

Entry point: [`quick_consume`](../../../apps/app_inventory/views.py:318) — POST `/entity/<entity_pk>/stock/consume/` from the stock detail page. Delegates to `ConsumptionOperation.create(...)` (the proven full pipeline: invoice item + auto `CONSUMPTION_MOVEMENT` + product `CONSUMED`; **no `Transaction` rows** — Consumption is a stock event, see [`op_19_consumption.md`](../operations/op_19_consumption.md)).

#### 5.4.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| QC1 | Officer staff | `request.user.is_staff` | redirect + message | `"You must be an officer to consume from stock."` | [`quick_consume`](../../../apps/app_inventory/views.py:339) | [`test_quick_consume_requires_officer`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:185) |
| QC2 | Product belongs to this stock | `product.entity == entity` | redirect + message | `"Product does not belong to this stock."` | [`quick_consume`](../../../apps/app_inventory/views.py:357) | [`test_quick_consume_rejects_product_not_in_entity`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:277) |
| QC3 | Template accepts consumption | `accepts_operation(CONSUMPTION)` | redirect + message | `"'…' cannot be consumed."` | [`quick_consume`](../../../apps/app_inventory/views.py:362) | [`test_quick_consume_rejects_non_consumable_nature`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:198) / [`test_quick_consume_rejects_non_consumable_flag`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:237) |
| QC4 | Quantity / price parse + positive | valid decimals, `qty > 0` | redirect + message | `"Invalid quantity or unit price."` / `"Quantity must be greater than zero."` | [`quick_consume`](../../../apps/app_inventory/views.py:369) | [`test_quick_consume_rejects_invalid_quantity`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:295) / [`test_quick_consume_rejects_invalid_unit_price`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:308) / [`test_quick_consume_rejects_zero_quantity`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:321) |
| QC5 | Availability | `qty ≤ movement_state(product, as_of=date)["quantity"]` | redirect + message | `"Insufficient stock: …"` | [`quick_consume`](../../../apps/app_inventory/views.py:391) | [`test_quick_consume_over_consumption_is_rejected`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:173) |
| QC6 | Unit consistency | `qty % minimum_quantity == 0` | redirect + message | `"Quantity … must be a multiple of the minimum increment …"` | [`quick_consume`](../../../apps/app_inventory/views.py:401) | [`test_quick_consume_rejects_quantity_not_multiple_of_minimum`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:334) |
| QC7 | Valid date | `parse_date` non-`None` | redirect + message | `"Invalid date format."` | [`quick_consume`](../../../apps/app_inventory/views.py:377) | [`test_quick_consume_rejects_invalid_date`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:350) |

#### 5.4.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| QS1 | Full pipeline in one POST | `ConsumptionOperation` + invoice item + auto movement line + product `CONSUMED` (no transactions) | `ConsumptionOperation.create` (atomic) | [`test_quick_consume_creates_full_pipeline`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:107) |
| QS2 | Partial consumption leaves remainder | `movement_state` reflects only the consumed portion | `movement_state` | [`test_quick_consume_partial_consumption`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:161) |
| QS3 | Over-consumption creates nothing | no op, product stays `ACTIVE` | whole view | [`test_quick_consume_over_consumption_is_rejected`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:173) |
| QS4 | Inline form rendered on stock detail | active consumable products show the quick-consume form | [`stock_detail`](../../../apps/app_inventory/views.py:25) | [`test_stock_detail_renders_quick_consume_form`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:143) |

### 5.5 `reverse movement`

Entry points: model [`InventoryMovementLine.reverse`](../../../apps/app_inventory/models.py:1238) / [`batch_reverse`](../../../apps/app_inventory/models.py:1260), views [`reverse_inventory_movement_line`](../../../apps/app_inventory/views.py:847) / [`batch_reverse_inventory_movement_lines`](../../../apps/app_inventory/views.py:887).

#### 5.5.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| MR1 | Line not already reversed | no `reversal_of=self` exists | `ValidationError` | `"Movement line … has already been reversed."` | [`InventoryMovementLine.reverse`](../../../apps/app_inventory/models.py:1243) | [`test_reverse_of_already_reversed_line_raises`](../../../apps/app_inventory/tests/test_inventory_movement.py:935) / [`test_reverse_movement_line_already_reversed_warns`](../../../apps/app_inventory/tests/test_views_movement_actions.py:105) |
| MR2 | Officer staff (view) | `request.user.is_staff` | redirect + message | `"You must be an officer to reverse movement lines."` | [`reverse_inventory_movement_line`](../../../apps/app_inventory/views.py:852) | [`test_reverse_movement_line_requires_officer`](../../../apps/app_inventory/tests/test_views_movement_actions.py:123) |

#### 5.5.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| MS1 | Reversal line created | clone with `reversal_of = original`, same op/item/product/qty | [`InventoryMovementLine.reverse`](../../../apps/app_inventory/models.py:1247) | [`test_reversed_movement_is_excluded`](../../../apps/app_inventory/tests/test_stock.py:135) |
| MS2 | Stock excludes both lines | reversal line **and** the reversed original are excluded from `active_movements` → net back to pre-move state | [`active_movements`](../../../apps/app_inventory/stock.py:31) | [`test_reversed_movement_is_excluded`](../../../apps/app_inventory/tests/test_stock.py:135) |
| MS3 | Item moved/remaining updated | `moved_qty` drops, `remaining_qty` rises; re-receiving the reversed amount passes the over-delivery guard | [`_item_moved_qty`](../../../apps/app_inventory/stock.py:147) / `build_movement_json` | [`test_get_items_data_excludes_reversed_movement_lines`](../../../apps/app_inventory/tests/test_inventory_movement.py:756) |
| MS4 | Batch reverse by `group_key` | all non-reversed lines sharing a key reversed atomically | [`batch_reverse`](../../../apps/app_inventory/models.py:1260) | [`test_batch_reverse_by_group_key`](../../../apps/app_inventory/tests/test_inventory_movement.py:943) / [`test_batch_reverse_success`](../../../apps/app_inventory/tests/test_views_movement_actions.py:165) |

### 5.6 `query` (state / portfolio / value / pending)

Pure functions in [`stock.py`](../../../apps/app_inventory/stock.py) — no side effects.

| # | Behavior | Verified by |
|---|----------|-------------|
| QV1 | `movement_state` is zero with no movements | [`test_state_zeros_without_movements`](../../../apps/app_inventory/tests/test_stock.py:104) |
| QV2 | Consumption valued at purchase price (70 kg / $140) | [`test_consumption_valued_at_purchase_price`](../../../apps/app_inventory/tests/test_stock.py:109) |
| QV3 | `as_of` before a movement excludes it | [`test_state_as_of_before_movement_is_zero`](../../../apps/app_inventory/tests/test_stock.py:126) |
| QV4 | Reversed movement excluded | [`test_reversed_movement_is_excluded`](../../../apps/app_inventory/tests/test_stock.py:135) |
| QV5 | Sale dispatch reduces seller stock | [`test_sale_dispatch_reduces_seller_stock`](../../../apps/app_inventory/tests/test_stock.py:147) |
| QV6 | Sale buyer receipt increases buyer stock | [`test_sale_buyer_receipt_increases_buyer_stock`](../../../apps/app_inventory/tests/test_stock.py:160) |
| QV7 | `portfolio` excludes zero-quantity products | [`test_portfolio_excludes_zero_quantity_products`](../../../apps/app_inventory/tests/test_stock.py:219) |
| QV8 | Written-off stock nets to zero; only on-hand remains in portfolio/value | [`test_portfolio_and_value_after_death_consumption_sale`](../../../apps/app_inventory/tests/test_stock.py:232) |
| QV9 | Pending inbound for an unreceived purchase | [`test_pending_inbound_for_unreceived_purchase`](../../../apps/app_inventory/tests/test_stock.py:318) |
| QV10 | No pending once received | [`test_no_pending_for_received_purchase`](../../../apps/app_inventory/tests/test_stock.py:334) |
| QV11 | Pending outbound for an undelivered sale | [`test_pending_outbound_for_undelivered_sale`](../../../apps/app_inventory/tests/test_stock.py:355) |

### 5.7 Immutability

`operation`, `invoice_item`, `quantity`, `product` **cannot be changed after save** — enforced by `ImmutableMixin` via `_immutable_fields` on `InventoryMovementLine`.

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `operation` changed after save | [`InventoryMovementLine._immutable_fields`](../../../apps/app_inventory/models.py:978) | [`test_movement_line_operation_is_immutable_after_save`](../../../apps/app_inventory/tests/test_inventory_movement.py:862) |
| `invoice_item` changed after save | [`InventoryMovementLine._immutable_fields`](../../../apps/app_inventory/models.py:978) | [`test_movement_line_invoice_item_is_immutable_after_save`](../../../apps/app_inventory/tests/test_inventory_movement.py:876) |
| `quantity` changed after save | [`InventoryMovementLine._immutable_fields`](../../../apps/app_inventory/models.py:978) | [`test_movement_line_quantity_is_immutable_after_save`](../../../apps/app_inventory/tests/test_inventory_movement.py:890) |
| `product` changed after save | [`InventoryMovementLine._immutable_fields`](../../../apps/app_inventory/models.py:978) | [`test_movement_line_product_is_immutable_after_save`](../../../apps/app_inventory/tests/test_inventory_movement.py:897) |

---

## 6. Period & financial-period contract

- The movement's governing entity is the parent operation's `period_entity` (`Operation.period_entity`).
- **Movements** dated inside a closed financial period of that entity are rejected (RC3/DC3) — enforced in `_create_inventory_movement` via `is_date_in_closed_period`.
- **Quick-consume** dates flow through `ConsumptionOperation.create(...)`, so the standard operation period guards apply (covering-period requirement, closed-period rejection).
- Reversals are exempt from the closed-period check and may land in a different open period (same exemption as operations).

---

## 7. Entity roles & balance contract

- **Owner of stock:** the `Product.entity` — the project whose inventory it belongs to. Movement lines may only move a product **out of** the entity that owns it (DC4/DC5) — `_outbound_owner_entity()` delegates to `Operation.inventory_owner_entity` so the ownership mapping lives in one place.
- **Direction-aware SALE:** a movement line is inbound when the product is owned by the SALE **source** (internal-client receipt), outbound when owned by the SALE **destination** (seller dispatch). This mirrors `movement_delta` and the stock-detail classification.
- **Availability:** outbound moves (SALE dispatch, DEATH, CONSUMPTION) never exceed `movement_state(product, as_of=date)["quantity"]`. SALE products created at sale time (never received) are **exempt** — the sale itself is what records them. DEATH/CONSUMPTION **always** enforce availability.
- **Status lifecycle:** a product's `status` is derived from its active movement lines — `ACTIVE` while net presence > 0, terminal (`SOLD`/`DEAD`/`CONSUMED`) after a full outbound dispatch/write-off, falling back to linked operations when no active moves remain (e.g. restored by reversal). Obligated-only products (registered but not moved) are blocked from downstream operations (`validate_active`).
- **Concurrency:** `Product.lock_ids` acquires row locks (`SELECT … FOR UPDATE`) around availability checks and movement inserts so concurrent movements on the same stock serialize (no-op on SQLite).

---

## 8. View / UI contract

| Concern | Behavior |
|---------|----------|
| Stock detail route | `GET /entity/<entity_pk>/stock/` → [`stock_detail`](../../../apps/app_inventory/views.py:25) |
| Live stock cards | only products with a **positive** net movement (`net_qty > 0` + `portfolio`); per-card qty/value; search by template name or tag; paginated |
| Obligated outbound | aggregate warning from `pending_items` with negative `pending_qty` |
| Quick-consume form | inline on stock detail for active consumable products → `POST /stock/consume/` |
| Stock history route | `GET /entity/<entity_pk>/stock/history/` → [`stock_history`](../../../apps/app_inventory/views.py:173) |
| History filters | direction (IN/OUT, reversal-aware), op type, search (tag/template), date range; IN/OUT counts; pending inbound/outbound panels |
| Product detail route | `GET /products/<pk>/` → [`product_detail`](../../../apps/app_inventory/views.py:454) — physical presence via `movement_state` |
| Receive form | `GET/POST /operations/<pk>/movement/create/purchase/` → [`create_purchase_movement`](../../../apps/app_inventory/views.py:615); budget JSON from `build_movement_json` |
| Dispatch form | `GET/POST /operations/<pk>/movement/create/sale/` → [`create_sale_movement`](../../../apps/app_inventory/views.py:630) |
| Backward-compatible route | `POST /operations/<pk>/movement/create/` redirects to the type-specific flow |
| Deferred movement | `GET/POST /operations/<pk>/movement/deferred/` → [`register_deferred_movements`](../../../apps/app_inventory/views.py:938); INDIVIDUAL → one line per Product, COMMODITY → one line full qty |
| Reverse movement | `GET/POST /movement-lines/<pk>/reverse/` and `POST /movement-lines/batch-reverse/<group_key>/` |
| Officer gating | every mutation view requires `request.user.is_staff` |

---

## 9. Branch catalog (all possible branches)

**receive — validation:** RC1 staff · RC2 op type PURCHASE · RC3 not closed period · RC4 over-delivery guard · RC5 unit increment · RC6 item belongs to op · RC7 no availability gate on inbound

**receive — effects:** RS1 movement line(s) · RS2 individual → one line per head (lazy tagged product) · RS3 commodity → one line full qty · RS4 product ACTIVE, state == received · RS5 receive after partial sale allowed · RS6 remaining qty ↓

**dispatch — validation:** DC1 staff · DC2 op type SALE · DC3 not closed period · DC4 ownership · DC5 ownerless rejected · DC6 availability · DC7 unreceived-sale exemption · DC8 over-delivery / unit

**dispatch — effects:** DS1 movement line · DS2 seller stock − · DS3 buyer receipt + · DS4 product SOLD · DS5 pending outbound ↓

**write off — validation:** WC1 availability always enforced · WC2 equal-to-on-hand allowed · WC3 nature/flag gating · **effects:** WS1 auto movement line · WS2 product DEAD/CONSUMED · WS3 stock nets to 0

**consume (quick) — validation:** QC1 staff · QC2 ownership · QC3 consumable nature/flag · QC4 qty/price parse + positive · QC5 availability · QC6 unit increment · QC7 valid date · **effects:** QS1 full pipeline · QS2 partial leaves remainder · QS3 over-consume creates nothing · QS4 inline form rendered

**reverse movement — validation:** MR1 not already reversed · MR2 staff · **effects:** MS1 reversal line · MS2 stock excludes both lines · MS3 moved/remaining updated, re-receive allowed · MS4 batch reverse by group_key

**query:** QV1 zero state · QV2 valued at purchase price · QV3 as_of excludes later moves · QV4 reversed excluded · QV5 sale dispatch − · QV6 buyer receipt + · QV7 portfolio excludes zero · QV8 written-off nets to zero · QV9 pending inbound · QV10 no pending once moved · QV11 pending outbound

**immutability:** IM1 operation · IM2 invoice_item · IM3 quantity · IM4 product (all immutable after save)

---

## 10. Test coverage matrix

| Area | Test method | Branch(es) |
|------|-------------|------------|
| `movement_state` | [`test_state_zeros_without_movements`](../../../apps/app_inventory/tests/test_stock.py:104) | QV1 |
| `movement_state` | [`test_consumption_valued_at_purchase_price`](../../../apps/app_inventory/tests/test_stock.py:109) | QV2 |
| `movement_state` | [`test_state_as_of_before_movement_is_zero`](../../../apps/app_inventory/tests/test_stock.py:126) | QV3 |
| `movement_state` | [`test_reversed_movement_is_excluded`](../../../apps/app_inventory/tests/test_stock.py:135) | QV4, MS2 |
| `movement_state` | [`test_sale_dispatch_reduces_seller_stock`](../../../apps/app_inventory/tests/test_stock.py:147) | QV5, DS2 |
| `movement_state` | [`test_sale_buyer_receipt_increases_buyer_stock`](../../../apps/app_inventory/tests/test_stock.py:160) | QV6, DS3 |
| `portfolio` / `inventory_value` | [`test_portfolio_excludes_zero_quantity_products`](../../../apps/app_inventory/tests/test_stock.py:219) | QV7 |
| `portfolio` / `inventory_value` | [`test_portfolio_and_value_after_death_consumption_sale`](../../../apps/app_inventory/tests/test_stock.py:232) | QV8, WS3 |
| `pending_items` | [`test_pending_inbound_for_unreceived_purchase`](../../../apps/app_inventory/tests/test_stock.py:318) | QV9 |
| `pending_items` | [`test_no_pending_for_received_purchase`](../../../apps/app_inventory/tests/test_stock.py:334) | QV10, RS6 |
| `pending_items` | [`test_pending_outbound_for_undelivered_sale`](../../../apps/app_inventory/tests/test_stock.py:355) | QV11, DS5 |
| Receive (view + model) | [`test_create_inventory_movement_purchase`](../../../apps/app_inventory/tests/test_inventory_movement.py:59) | RS1–RS4 |
| Receive (view + model) | [`test_purchase_movement_creates_new_product_per_animal`](../../../apps/app_inventory/tests/test_inventory_movement.py:120) | RS2 |
| Receive (view) | [`test_non_staff_cannot_create_movement`](../../../apps/app_inventory/tests/test_inventory_movement.py:183) | RC1 |
| Dispatch (view) | [`test_sale_operation_movement`](../../../apps/app_inventory/tests/test_inventory_movement.py:203) | DS1, DC7 |
| Receive (validation) | [`test_quantity_exceeds_invoice_item`](../../../apps/app_inventory/tests/test_inventory_movement.py:245) | RC4 |
| Dispatch (validation) | [`test_sale_movement_rejects_product_owned_by_another_entity`](../../../apps/app_inventory/tests/test_inventory_movement.py:310) | DC4 |
| Dispatch (validation) | [`test_sale_movement_rejects_product_without_owner`](../../../apps/app_inventory/tests/test_inventory_movement.py:327) | DC5 |
| Dispatch (validation) | [`test_sale_movement_accepts_product_owned_by_selling_project`](../../../apps/app_inventory/tests/test_inventory_movement.py:343) | DC4 pass |
| Receive (model) | [`test_purchase_lazy_product_belongs_to_project`](../../../apps/app_inventory/tests/test_inventory_movement.py:358) | RS2/RS4 |
| Ownership helper | [`test_outbound_owner_entity_delegates_to_operation`](../../../apps/app_inventory/tests/test_inventory_movement.py:380) | DC4 helper |
| Availability | [`test_sale_movement_rejects_qty_beyond_on_hand`](../../../apps/app_inventory/tests/test_inventory_movement.py:490) | DC6 |
| Availability | [`test_death_movement_rejects_qty_beyond_on_hand`](../../../apps/app_inventory/tests/test_inventory_movement.py:497) | WC1 |
| Availability | [`test_consumption_movement_rejects_qty_beyond_on_hand`](../../../apps/app_inventory/tests/test_inventory_movement.py:504) | WC1 |
| Availability | [`test_death_movement_accepts_qty_equal_to_on_hand`](../../../apps/app_inventory/tests/test_inventory_movement.py:523) | WC2 |
| Unit consistency | [`test_invoice_item_rejects_quantity_not_multiple_of_minimum`](../../../apps/app_inventory/tests/test_inventory_movement.py:533) | RC5 (item) |
| Unit consistency | [`test_movement_rejects_quantity_not_multiple_of_minimum`](../../../apps/app_inventory/tests/test_inventory_movement.py:546) | RC5 |
| Unit consistency | [`test_movement_accepts_quantity_multiple_of_minimum`](../../../apps/app_inventory/tests/test_inventory_movement.py:569) | RC5 pass |
| Receive after partial sale | [`test_purchase_receive_remaining_after_partial_sale`](../../../apps/app_inventory/tests/test_inventory_movement.py:595) | RS5 |
| Op-type mismatch | [`test_sale_movement_rejects_operation_mismatch`](../../../apps/app_inventory/tests/test_inventory_movement.py:686) | RC2 / DC2 |
| Reversal → moved qty | [`test_get_items_data_excludes_reversed_movement_lines`](../../../apps/app_inventory/tests/test_inventory_movement.py:756) | MS3, RC4-after-reverse |
| Reversal → detail | [`test_operation_detail_shows_reduced_moved_qty_after_reversal`](../../../apps/app_inventory/tests/test_inventory_movement.py:806) | MS3 (UI) |
| Quick consume | [`test_quick_consume_creates_full_pipeline`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:107) | QS1, WS2/WS3 |
| Quick consume | [`test_quick_consume_partial_consumption`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:161) | QS2 |
| Quick consume | [`test_quick_consume_over_consumption_is_rejected`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:173) | QC5, QS3 |
| Quick consume | [`test_quick_consume_requires_officer`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:185) | QC1 |
| Quick consume | [`test_quick_consume_rejects_non_consumable_nature`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:198) | QC3 (nature) |
| Quick consume | [`test_quick_consume_rejects_non_consumable_flag`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:237) | QC3 (flag) |
| Quick consume | [`test_quick_consume_rejects_product_not_in_entity`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:277) | QC2 |
| Quick consume (UI) | [`test_stock_detail_renders_quick_consume_form`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:143) | QS4 |
| Stock detail view | [`test_views_get_stock_detail_view.py`](../../../apps/app_inventory/tests/test_views_get_stock_detail_view.py) | view contract (§8) |
| Stock history view | [`test_views_get_stock_history_view.py`](../../../apps/app_inventory/tests/test_views_get_stock_history_view.py) | view contract (§8) |
| Product valuation | [`test_product.py`](../../../apps/app_inventory/tests/test_product.py:195) | `current_value` basis (+ capital gain/loss) |
| Immutability | [`test_movement_line_operation_is_immutable_after_save`](../../../apps/app_inventory/tests/test_inventory_movement.py:862) | IM1 |
| Immutability | [`test_movement_line_invoice_item_is_immutable_after_save`](../../../apps/app_inventory/tests/test_inventory_movement.py:876) | IM2 |
| Immutability | [`test_movement_line_quantity_is_immutable_after_save`](../../../apps/app_inventory/tests/test_inventory_movement.py:890) | IM3 |
| Immutability | [`test_movement_line_product_is_immutable_after_save`](../../../apps/app_inventory/tests/test_inventory_movement.py:897) | IM4 |
| Receive (validation) | [`test_movement_rejects_invoice_item_from_other_operation`](../../../apps/app_inventory/tests/test_inventory_movement.py:907) | RC6 |
| Receive (model) | [`test_purchase_commodity_receives_single_line_full_qty`](../../../apps/app_inventory/tests/test_inventory_movement.py:984) | RS3 |
| Reversal (model) | [`test_reverse_of_already_reversed_line_raises`](../../../apps/app_inventory/tests/test_inventory_movement.py:935) | MR1 |
| Reversal (view) | [`test_reverse_movement_line_success`](../../../apps/app_inventory/tests/test_views_movement_actions.py:86) | MS1, MS2 |
| Reversal (view) | [`test_reverse_movement_line_already_reversed_warns`](../../../apps/app_inventory/tests/test_views_movement_actions.py:105) | MR1 |
| Reversal (view) | [`test_reverse_movement_line_requires_officer`](../../../apps/app_inventory/tests/test_views_movement_actions.py:123) | MR2 |
| Reversal (model) | [`test_batch_reverse_by_group_key`](../../../apps/app_inventory/tests/test_inventory_movement.py:943) | MS4 |
| Reversal (view) | [`test_batch_reverse_success`](../../../apps/app_inventory/tests/test_views_movement_actions.py:165) | MS4 |
| Quick consume (validation) | [`test_quick_consume_rejects_invalid_quantity`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:295) | QC4 |
| Quick consume (validation) | [`test_quick_consume_rejects_invalid_unit_price`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:308) | QC4 |
| Quick consume (validation) | [`test_quick_consume_rejects_zero_quantity`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:321) | QC4 |
| Quick consume (validation) | [`test_quick_consume_rejects_quantity_not_multiple_of_minimum`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:334) | QC6 |
| Quick consume (validation) | [`test_quick_consume_rejects_invalid_date`](../../../apps/app_inventory/tests/test_quick_consume_from_stock.py:350) | QC7 |
| Deferred movements (view) | [`test_register_deferred_movements_commodity_single_line`](../../../apps/app_inventory/tests/test_views_movement_actions.py:205) | §8 deferred (COMMODITY) |
| Deferred movements (view) | [`test_register_deferred_movements_individual_one_line_per_product`](../../../apps/app_inventory/tests/test_views_movement_actions.py:251) | §8 deferred (INDIVIDUAL) |
| Deferred movements (view) | [`test_register_deferred_movements_requires_officer`](../../../apps/app_inventory/tests/test_views_movement_actions.py:285) | §8 deferred officer gate |
| View contract | [`test_backward_compatible_movement_route_redirects`](../../../apps/app_inventory/tests/test_views_movement_actions.py:311) | §8 backward-compatible route |
