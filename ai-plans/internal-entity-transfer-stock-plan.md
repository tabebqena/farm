# Analysis & Regression Report — Internal-Entity Transfer via SALE only (rev 4)

**Status:** analysis only (implementation deferred by user, 2026-08-12). Rev 4 supersedes
rev 3 — the strategy is **reversed** per the user:

> "Block the purchase between internal entities & allow sale. The sale operation preselects
> the product, so we know the product, product template, qty etc."

**Scope:** what happens today when a SALE or PURCHASE occurs between two **internal** entities
(`Entity.is_internal == True`), the intended behavior, the chosen strategy, and the regression
risk.

## User decisions (2026-08-12) — the strategy

1. **Block PURCHASE between internal entities.** An internal entity cannot be a vendor; the
   internal-vendor purchase path is **blocked** (not fixed). Purchases become external-only.
2. **Allow SALE between internal entities** — the SALE is the **intra-farm stock-transfer
   mechanism**. Because the sale now **preselects the seller's existing product**, we know
   exactly which product, product template, quantity and price are moving, so both sides are
   fully determined:
   - **Seller side:** the existing product is dispatched (`SALE_MOVEMENT`) → `SOLD`, leaves
     the seller's stock (already implemented in the sale fix).
   - **Buyer side (new):** the internal client receives the goods — a product row owned by the
     client (`ACTIVE`) that appears in the client's stock.
3. **`Product.status`** is made **direction-aware** (combine linked operation type + side) so
   a buyer-owned product on a SALE resolves to `ACTIVE` and a seller-owned product to `SOLD`.
4. **Minimal code**, avoid silently breaking already-implemented functionality.

An "internal entity" is any `Entity` with `is_internal=True`
([`Entity.is_internal`](../apps/app_entity/models/__init__.py:245)); SYSTEM is forced
internal, WORLD forced non-internal ([`Entity.clean()`](../apps/app_entity/models/__init__.py:321)).

---

## 1. Intended behavior (updated)

- **PURCHASE (internal vendor):** **blocked** — internal entities are excluded from the
  vendor list and rejected in [`PurchaseOperation.clean_destination()`](../apps/app_operation/models/proxies/op_purchase.py:75)
  with a clear message. No vendor-side stock concern exists.
- **SALE (internal client):** **allowed** — it is the transfer mechanism. The seller's
  existing product leaves the seller's stock (`SOLD`), and the internal client **receives** an
  equivalent product (`ACTIVE`) in its stock.

The net effect: goods move **project → internal project** via a sale; purchases are
external-only. No double-counting.

---

## 2. Current behavior (verified)

### 2.1 PURCHASE from an internal vendor — today it double-counts (to be blocked)

In [`PurchaseOperation.create_from_session()`](../apps/app_operation/models/proxies/op_purchase.py:96):

| Side | What happens | Stock effect |
|---|---|---|
| **Buyer** (project = source) | inbound `PURCHASE_MOVEMENT` lazily creates products owned by the buyer → `ACTIVE` | **Works.** Appears in the buyer's live stock. |
| **Vendor** (internal entity = destination) | **Nothing** touches the vendor's stock | The internal vendor keeps the goods live/ACTIVE → **double-count** |

**Blocking** this (removing internal entities from the vendor list + a `clean_destination`
guard) removes the double-count without needing a vendor-side reduction.

### 2.2 SALE with an internal client — today only the seller side works

In [`SaleOperation.create_from_session()`](../apps/app_operation/models/proxies/op_sale.py:96)
(the sale fix, rev 3):

| Side | What happens | Stock effect |
|---|---|---|
| **Seller** (project = destination) | the selected existing product is linked to the SALE item and a `SALE_MOVEMENT` line is recorded against it | Product leaves the seller's live stock; status `SOLD`. **Works.** |
| **Buyer** (internal client = source) | **nothing** — the internal-client clone block was removed | The client does not receive the goods |

**To allow** internal-client sales, the buyer side must be added: the client receives an
`ACTIVE` product (see §3.2).

---

## 3. The design

### 3.1 PURCHASE — block internal vendors

1. Exclude `is_internal=True` from the vendor list:
   - [`PurchaseOperation.get_related_entities()`](../apps/app_operation/models/proxies/op_purchase.py:63)
   - `PurchaseWizardStep1Form` vendor queryset ([`forms.py`](../apps/app_operation/forms.py:10))
2. Reject internal sources in [`PurchaseOperation.clean_destination()`](../apps/app_operation/models/proxies/op_purchase.py:75):
   *"Internal entities cannot be vendors. To transfer goods between internal entities, record
   a sale from the other side."*
3. Result: purchases are external-only; no vendor-side stock logic is needed.

### 3.2 SALE — allow internal clients and record the buyer's receipt

In [`SaleOperation.create_from_session()`](../apps/app_operation/models/proxies/op_sale.py:96),
when `client.is_internal`:

1. **Seller side (unchanged):** the selected existing product is dispatched
   (`SALE_MOVEMENT`, `SOLD`).
2. **Buyer side (new):** create the buyer's receipt using the sale's known data
   (`product`, `product_template`, `quantity`, `unit_price`):
   - **COMMODITY:** one product owned by the client, qty = sold qty, template = the seller's
     template.
   - **INDIVIDUAL:** one product per sold animal owned by the client (the sale preselects the
     specific animals, so the buyer's copies mirror them).
   - **Valuation:** the buyer's carried `unit_price` = the sale price (what the client paid) —
     confirm as an open decision.
   - Link the buyer's product(s) to the SALE invoice item (provenance).
3. **Direction-aware `Product.status`** ([`models.py`](../apps/app_inventory/models.py:1091)):
   - product owned by the SALE **source** (client = buyer) → `ACTIVE`
   - product owned by the SALE **destination** (project = seller) → `SOLD`
4. **Buyer visibility:** the buyer's product must appear in the client's live stock. Two
   options:
   - **(a) Inbound movement on the SALE op** for the buyer's product, with a direction-aware
     [`record_movement_line()`](../apps/app_inventory/models.py:302) (source-owned on SALE →
     `+`; destination-owned → `−`). Appears in `stock_detail` "live" + `stock_history`.
   - **(b) Direct inbound `ProductLedgerEntry`** for the buyer's product (no movement line) +
     stock-view support. Simpler vs. the ownership guard, but needs view changes.
   Recommend (a) — it reuses movement-line mechanics.
5. **Reversal:** reversing the internal-client sale restores the seller's product (`ACTIVE`,
   Fix 8) and removes the buyer's receipt (negate the buyer movement/ledger; buyer product
   resolves back to removed/ACTIVE via reversal-aware direction status).

### 3.3 Enabler — direction-aware status + ledger (shared)

- `Product.status`: combine operation type **and** side (receiver → ACTIVE, disposer → SOLD).
- `record_movement_line`: emit `+`/`−` per product ownership side on the same operation.

---

## 4. Regression risk assessment

- **PURCHASE blocking:** medium-low. Touches `get_related_entities`, the wizard vendor queryset,
  and `clean_destination`. Existing purchase tests use **external** vendors (`is_vendor=True`,
  not internal) → unaffected. Wizard vendor-list tests must still pass (internal vendors were
  not commonly added). Add tests for the new rejection.
- **SALE buyer receipt:** medium. Reuses `create_products_for_item` for the buyer side (the
  method the sale fix removed from the seller path), plus direction-aware status/ledger.
  - The seller-side behavior (external clients) must remain identical → external client sales
    unaffected.
  - `Product.status` direction-aware change must not alter external-client status results
    (seller-owned on SALE → SOLD as today).
  - The ownership guard ([`InventoryMovementLine.clean()`](../apps/app_inventory/models.py:1537))
    is **not** triggered in `create_from_session` (direct `.objects.create()`), but any later
    movement view touching the buyer's product must account for it.
- **No new ledger entry types** required if direction-aware movement recording is used; no
  migration for status (derived).

---

## 5. Recommended sequence

1. **Direction-aware `Product.status` + `record_movement_line`** (foundation; external flows
   unchanged) with tests.
2. **Purchase blocking:** exclude internal vendors (list + wizard) + `clean_destination` guard
   + tests.
3. **Sale buyer receipt:** in `create_from_session`, when `client.is_internal`, create the
   buyer's product + inbound movement (direction-aware) so it appears `ACTIVE` in the client's
   stock; tests.
4. **Reversal symmetry** for internal-client sales + tests.
5. **Docs/specs** update (`op_13_purchase.md`, `op_14_sale.md`, Fix 7 note, mechanism review).
6. **Regression run** (targeted + `manage.py test --parallel=8`).

---

## 6. Decisions (2026-08-12)

1. **Buyer valuation = sale `unit_price`.** The buyer's carried cost is the transfer price it
   paid (the sale `unit_price`), not the seller's carried cost. Consistent with the existing
   valuation basis (`Product.unit_price` = carried cost) and reflects the economic transfer.
2. **Buyer visibility = inbound movement on the SALE op** with **direction-aware**
   [`record_movement_line()`](../apps/app_inventory/models.py:302):
   - source-owned product (the internal client) → `PURCHASE_MOVEMENT +` (receipt)
   - destination-owned product (the seller) → `SALE_MOVEMENT −` (dispatch)
   Both types are already in `MOVEMENT_TYPES` → no migration, no view changes, reversal handled
   by the existing movement-reversal mechanism.
3. **`Product.status` = direction-aware now; disposal-aware (per-quantity) deferred.** Implement
   direction-aware status (source-owned on a SALE → `ACTIVE`; destination-owned → `SOLD`) as
   part of the internal-transfer work — additive and does not change external-client results.
   The per-product limitation (a partial commodity sale marks the whole product `SOLD`, so the
   remaining on-hand is blocked) is a **separate, broader follow-up** (quantity/disposal-aware
   status) and is tracked under the "remaining issues" list.
4. **Sale reversal UX:** every wizard sale creates a movement line, so reversing a sale requires
  reversing its movement lines first (existing guard). Accepted for now.

---

## 7. Implementation status (2026-08-12)

Implemented and verified — full suite green (1440 tests OK via `manage.py test --parallel=8`).

- **Direction-aware `Product.status`** ([`models.py`](../apps/app_inventory/models.py:1091)):
 receiver side → ACTIVE, disposer side → SOLD/DEAD/CONSUMED, with the historical op-type
 mapping as fallback (external flows unchanged).
- **Direction-aware `record_movement_line`** ([`models.py`](../apps/app_inventory/models.py:296)):
 on a SALE, a source-owned product (the internal client's receipt) records `PURCHASE_MOVEMENT +`;
 a destination-owned product (the seller's dispatch) records `SALE_MOVEMENT −`.
- **PURCHASE blocking:** internal entities excluded from
 [`get_related_entities()`](../apps/app_operation/models/proxies/op_purchase.py:63) and
 `PurchaseWizardStep1Form`; [`clean_destination()`](../apps/app_operation/models/proxies/op_purchase.py:75)
 rejects internal vendors.
- **SALE buyer receipt:** [`create_from_session()`](../apps/app_operation/models/proxies/op_sale.py:96)
 creates the internal client's `ACTIVE` product (sale `unit_price`) and its inbound receipt
 movement.
- **Buyer visibility:** [`stock_detail`](../apps/app_inventory/views.py:25) classifies a SALE
 movement by ownership (source-owned → incoming) so the buyer copy appears in the buyer's live
 stock; [`portfolio_as_of`](../apps/app_inventory/models.py:381) now matches by `product__entity`.
 The movement ownership/availability guard
 ([`_outbound_owner_entity`](../apps/app_inventory/models.py:1558)) treats the buyer receipt as
 inbound; `build_movement_json` and the over-delivery guard count movements per owner.
- **Tests:** added buyer-receipt, external-client-no-copy, purchase-blocking, direction-aware
 status, buyer-in-stock, and receipt-reversal tests.
- **Not done (documented):** full operation-level reversal convenience for internal-client sales
 (movements must be reversed first — existing guard); disposal-aware (per-quantity) status.
4. **Sale reversal UX:** every wizard sale creates a movement line, so reversing a sale
   requires reversing its movement lines first (existing guard). Accepted for now; a
   convenience (reverse movements with the operation) is a possible later enhancement.
