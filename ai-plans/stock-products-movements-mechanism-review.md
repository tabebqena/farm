# Stock / Products / Movements — Mechanism Review

**Status:** analysis only (implementation deferred). Companion to
`internal-entity-transfer-stock-plan.md`.

**User decisions (2026-08-12):**
- Multi-step fix.
- **Keep the sale wizard** and make it **affect the already-present product** (the seller's
  existing stock) — no fresh-product minting.
- **Remove the other sale path** (`SaleCreateView` / `sale_form.html` and the generic
  `operation_create_view` sale branch) — the wizard becomes the only sale path.
- After the SALE fix, **recheck the whole issue** (purchase, sale, internal, external,
  product status, etc.).

## 1. The principle (user-stated)

- **A Product resembles the presence of something** — a persistent physical-stock record
  owned by an entity (an individual animal, or a commodity lot/quantity).
- **Movement lines affect the product** — an inbound movement creates/increases its presence;
  an outbound movement reduces/removes it.
- Therefore **products are created only when presence begins** (a received purchase, a birth),
  and **outbound operations (sale / death / consumption) AFFECT existing products** — they
  must never mint a new product as a terminal artifact.

The corollary for a purchase from an internal vendor: the vendor's product **already exists**
in its stock; the purchase records an outbound movement against that existing product.

## 2. The current mechanism (verified)

### 2.1 Data model

| Model | Role |
|---|---|
| [`Product`](../apps/app_inventory/models.py:1012) | physical presence: `entity` owner, `product_template`, `quantity`, `unique_id` (tag), derived `status`, M2M `invoice_items` (the operations that touched it) |
| [`InvoiceItem`](../apps/app_inventory/models.py:795) | contract line (what was ordered/sold); has `product_template`, `quantity`, `unit_price`, M2M `products` |
| [`InventoryMovementLine`](../apps/app_inventory/models.py:1422) | the event that affects a product: `operation`, `invoice_item`, `product`, `quantity`, `date`, `reversal_of` |
| [`ProductLedgerEntry`](../apps/app_inventory/models.py:37) | append-only idempotent ledger row for issuances & movements; drives availability, valuation, portfolio |
| [`Operation`](../apps/app_operation/models/operation.py) | business event tying contract + movement + financial transaction |

### 2.2 How each operation currently affects stock

| Op | Buyer/Receiver side | Seller/Vendor side |
|---|---|---|
| **PURCHASE** (wizard [`create_from_session`](../apps/app_operation/models/proxies/op_purchase.py:96)) | inbound `PURCHASE_MOVEMENT` lazily creates buyer product → `ACTIVE` | external vendor: n/a. **internal vendor: untouched (BUG)** |
| **SALE** (wizard [`create_from_session`](../apps/app_operation/models/proxies/op_sale.py:96)) | — | **creates a fresh `SOLD` product** via [`create_products_for_item`](../apps/app_inventory/models.py:895) — does NOT affect the seller's existing stock |
| **SALE** (standard view [`OperationCreateView`](../apps/app_operation/views/create_operation/base.py:75) → [`Operation.create`](../apps/app_operation/models/operation.py:344)) | — | uses [`InvoiceItemSelectFormSet`](../apps/app_inventory/forms.py:398) to **select existing** products; but [`save_inventory`](../apps/app_operation/models/operation.py:806) for SALE only writes issuance — the selection is not linked into a movement at create time |
| **BIRTH** | inbound movement lazily creates product → `ACTIVE` | system |
| **DEATH / CONSUMPTION** | — | auto-create movements against **existing** selected products → `DEAD`/`CONSUMED` ([`_auto_create_inventory_movements`](../apps/app_operation/models/operation.py:870)) |

### 2.3 The two SALE paths diverge

- **Wizard path** (`sale_wizard` → `sale_invoice` → `SaleItemForm` collecting
  `product_template_id/quantity/price/delivered_qty` → `create_from_session`): **mints fresh
  SOLD products** for the seller and (if internal client) a fresh clone. It never lets the
  user pick an existing product.
- **Standard path** (`SaleCreateView` → `sale_form.html`): uses `InvoiceItemSelectFormSet`
  so the user **selects an existing product** — but `save_inventory` does not create the
  movement; the officer must record it later via
  [`create_inventory_movement`](../apps/app_inventory/views.py:602).

This inconsistency is part of the deeper error: the same concept (a sale) is implemented two
different ways with different stock semantics.

## 3. The deep errors

1. **SALE wizard mints fresh `SOLD` products** instead of affecting the seller's existing
   on-hand product. Effect: the seller's real stock is NOT reduced (only paper `SOLD` rows
   are added), availability against real stock is bypassed for these fresh products
   ([`_validate_availability`](../apps/app_inventory/models.py:1503) exempts sale-created
   products), and the two sale paths disagree.
2. **Standard SALE path is half-wired**: the selected existing product is not turned into a
   movement at create time (issuance only), so selection alone does not reduce stock until an
   officer records a movement.
3. **PURCHASE from an internal vendor does not reduce the vendor's existing stock**
   → the same goods are present in both entities → double-count (the critical bug).
4. **SALE to an internal client creates a fresh clone** (status `SOLD`, no movement, no
   ledger) — invisible in the buyer's live stock.
5. **`Product.status` is operation-type-only, not direction-aware**
   ([`Product.status`](../apps/app_inventory/models.py:1091)) — it cannot express "vendor side
   of a purchase is SOLD" or "buyer side ACTIVE".
6. **`record_movement_line` signs by operation type only** (single direction per op)
   ([`record_movement_line`](../apps/app_inventory/models.py:302)) — one operation cannot
   record both the buyer's inbound and the vendor's outbound.

## 4. The corrected mechanism

Invariant: **products are created only on inbound (purchase-received / birth); outbound ops
affect existing products.**

| Op | Buyer/Receiver side | Seller/Vendor side |
|---|---|---|
| **PURCHASE** (external vendor) | inbound movement creates buyer product → `ACTIVE` | — |
| **PURCHASE** (internal vendor) | **blocked** (internal entities cannot be vendors) | — |
| **SALE** (external client) | — | user picks the seller's **existing** product; `SALE_MOVEMENT` affects it → `SOLD`, real stock reduced |
| **SALE** (internal client) | buyer **receives** an `ACTIVE` product (clone via direction-aware status) | seller's **existing** product → `SOLD` |
| **BIRTH** | inbound movement creates product → `ACTIVE` | — |
| **DEATH / CONSUMPTION** | — | movement against existing product → `DEAD`/`CONSUMED` |

Enablers (shared):

- **Direction-aware status**: [`Product.status`](../apps/app_inventory/models.py:1091)
  combines the linked operation type **and** the product's side (receiver → ACTIVE;
  disposer → SOLD/DEAD/CONSUMED).
- **Direction-aware ledger**: [`record_movement_line`](../apps/app_inventory/models.py:302)
  emits the movement sign per product ownership side on the same operation (source-owned on a
  SALE → receive `+`; destination-owned → dispatch `−`; both entry types already in
  `MOVEMENT_TYPES`).
- **Availability**: outbound always checked against the entity's on-hand stock (Fix 2).

## 5. Impact / regression

- The SALE mechanism fix is **implemented** (rev 3): the wizard selects the seller's existing
  product and `SALE_MOVEMENT` affects it; the other sale path is removed.
- Remaining work per the rev-4 strategy: **block internal-vendor purchases** and **add the
  internal-client sale buyer receipt** (both reuse the direction-aware enablers).
- No new ledger entry types; no migration required for the enablers (status is derived;
  movement types already exist).

## 6. Recommended sequence (rev-4 strategy)

1. **Foundation: direction-aware `Product.status` + direction-aware `record_movement_line`**
   (with tests that external flows are unchanged).
2. **PURCHASE blocking:** exclude internal entities from the vendor list
   ([`get_related_entities()`](../apps/app_operation/models/proxies/op_purchase.py:63) +
   `PurchaseWizardStep1Form`) and reject internal vendors in
   [`clean_destination()`](../apps/app_operation/models/proxies/op_purchase.py:75); tests.
3. **SALE buyer receipt:** in [`SaleOperation.create_from_session()`](../apps/app_operation/models/proxies/op_sale.py:96),
   when `client.is_internal`, create the buyer's `ACTIVE` product (same template/qty/price) and
   record its receipt via the direction-aware movement path; tests.
4. **Reversal symmetry** for internal-client sales (restore seller product, remove buyer
   receipt) + tests.
5. **Docs/specs** update (`op_13_purchase.md`, `op_14_sale.md`, Fix 7 note).
6. **Regression run** (targeted + `manage.py test --parallel=8`).

## 7. Open questions

- **Buyer receipt valuation:** buyer's carried `unit_price` = sale price (cost to the client)
  vs. the seller's carried cost.
- **Buyer visibility mechanism:** inbound movement on the SALE op (direction-aware) vs. a
  direct ledger entry + view support.
- **`Product.status` is per-product, not per-quantity** — a partial commodity sale marks the
  whole product `SOLD`, blocking the remaining on-hand from further use.
- **Sale reversal UX:** every wizard sale creates a movement line, so reversing requires
  reversing movements first.
