# Plan: Internal-Entity Sale/Purchase — Stock Transfer Semantics

**Source of truth:** verified against `apps/app_operation/models/proxies/op_sale.py`,
`apps/app_operation/models/proxies/op_purchase.py`, `apps/app_inventory/models.py`,
`apps/app_inventory/views.py`, `apps/app_entity/models/__init__.py`, and the existing
plans `ai-plans/inventory-integrity-fixes-plan.md` (Fix 7) and
`ai-plans/stock-detail-and-history-plan.md`.

## Problem statement

When a SALE or PURCHASE happens between **two internal entities**, the physical stock
should move:

- **SALE (internal client):** the product is removed from the seller's stock, and an
  equivalent line appears in the buyer's stock.
- **PURCHASE (internal vendor):** the reverse — the product is removed from the vendor's
  stock and appears in the buyer's stock.

Question to answer: what is the effect today, and is there any regression when we make
this behavior correct/complete?

## Current behavior (verified by code reading)

### SALE with an internal client — implemented but only partially correct

In [`SaleOperation.create_from_session()`](apps/app_operation/models/proxies/op_sale.py:187):

1. **Seller (project/destination)** — `InvoiceItem.create_products_for_item(...)` creates
   `Product` rows owned by the project, linked to the SALE `InvoiceItem`
   → `Product.status == SOLD` ([`Product.status`](apps/app_inventory/models.py:1091)).
   If `delivered_qty > 0` an outbound `SALE_MOVEMENT` line is created → appears in the
   "sold" tab of `stock_detail`. Without a movement line the product is net-zero and only
   shows in the "all" branch — either way it is out of the "live" stock.
2. **Buyer (internal client/source)** — a **clone** `Product` is created owned by the
   client, but:
   - It is linked to the **same SALE `InvoiceItem`** → `Product.status == SOLD`, not ACTIVE.
   - It gets **no movement line and no ledger entry** → in `stock_detail` "live" it is
     invisible (net 0), and it is not in the "sold" tab either (no SALE movement line).
   - The buyer's physically-present summary (`ProductLedgerEntry.portfolio_as_of`) does
     **not** include the clone, so buyer inventory value understates the transferred stock.

**Conclusion:** the clone row exists (matches "another line resembling the same product"),
but the documented intent in [`op_14_sale.md`](specs/operations/op_14_sale.md:25) and Fix 7
("client copy becomes ACTIVE in the client's stock") is **only partially realized**. The
buyer sees a SOLD product that is not in their live stock.

### PURCHASE with an internal vendor — not implemented

In [`PurchaseOperation.create_from_session()`](apps/app_operation/models/proxies/op_purchase.py:96):

1. **Buyer (project/source)** — products are lazily created via inbound movement lines
   → `ACTIVE` and in the buyer's "live" stock. **Works.**
2. **Vendor (internal destination)** — **nothing** touches the vendor's stock. The vendor
   still shows the sold product as available/live. This is the missing "reverse".

## The design constraint (why this is not a one-liner)

- **Movement ownership guard (Fix 1):** [`InventoryMovementLine.clean()`](apps/app_inventory/models.py:1537)
  requires that for outbound ops (SALE) the moved `product.entity` equals
  `operation.inventory_owner_entity` (the selling project). A buyer-owned clone cannot get
  a movement line on the SALE op.
- **Movement direction is op-type based:** SALE → outgoing (−), PURCHASE → incoming (+).
  One operation cannot express both the seller's outbound and the buyer's inbound through
  `InventoryMovementLine`.
- **`Product.status` is derived from linked operations** via `invoice_items`, not from the
  ledger — so a clone linked to the SALE op resolves to SOLD, and a clone linked to the
  PURCHASE op resolves to ACTIVE, regardless of intent.

## Recommended approach

Introduce a small, explicit **internal-transfer stock effect** recorded in the ledger and
surfaced in the stock views, rather than bending the op-directional movement lines:

1. Add two entry types to `ProductLedgerEntry.EntryType` and `MOVEMENT_TYPES`:
   - `INTERNAL_TRANSFER_IN` (positive qty/value) — stock received by the buyer/client.
   - `INTERNAL_TRANSFER_OUT` (negative qty/value) — stock disposed by the seller/vendor.
2. **SALE (internal client):** keep the seller's SOLD product + optional movement; for the
   buyer clone record an `INTERNAL_TRANSFER_IN` ledger entry so the buyer's physically
   present summary and stock list include it, and make `Product.status` resolve the
   transfer-in clone to `ACTIVE`.
3. **PURCHASE (internal vendor):** buyer products stay as today (inbound movement);
   additionally create a disposal clone for the vendor and record an
   `INTERNAL_TRANSFER_OUT` ledger entry so the vendor's stock excludes it, with
   `Product.status` resolving to SOLD/REMOVED.
4. **`stock_detail` "live" tab** must include transfer-in clones. Either (a) add a scoped
   movement for the clone with an internal-transfer exception to the ownership guard, or
   (b) extend the "live" filter to also include products with a positive
   `INTERNAL_TRANSFER_IN` ledger net. Coordinate with `ai-plans/stock-detail-and-history-plan.md`.
5. **Reversal symmetry (Fix 8):** reversing an internal-entity SALE/PURCHASE must negate
   the transfer ledger entries (idempotent REVERSAL pattern) and restore statuses
   (buyer clone no longer ACTIVE, vendor product restored if it was a removal).
6. **Docs:** update `op_13_purchase.md`, `op_14_sale.md`, and
   `ai-plans/inventory-integrity-fixes-plan.md` Fix 7 note to match the new semantics.

## Implementation steps (todo)

- [ ] Write failing tests that pin current internal-entity SALE/PURCHASE stock behavior
      (buyer clone status/visibility; vendor stock untouched).
- [ ] Add `INTERNAL_TRANSFER_IN` / `INTERNAL_TRANSFER_OUT` ledger entry types +
      migration + `MOVEMENT_TYPES` membership.
- [ ] SALE: record transfer-in for the internal-client clone; adjust `Product.status` to
      ACTIVE for transfer-in clones.
- [ ] PURCHASE: create vendor disposal clone + transfer-out ledger; adjust `Product.status`
      for transfer-out clones.
- [ ] Surface transfer clones in `stock_detail` (live tab + summary) without weakening the
      Fix 1 ownership guard.
- [ ] Handle reversal of internal-entity SALE/PURCHASE (negate transfer entries, restore
      statuses) and add reversal tests.
- [ ] Update specs/docs (`op_13`, `op_14`, inventory-integrity Fix 7 note).
- [ ] Regression run: targeted sale/purchase/inventory/period tests, then full suite
      (`manage.py test --parallel=8`).

## Regression analysis

- **Low risk:** the sale/purchase wizard already creates the clone; we only change its
  ledger/status representation. No existing test asserts the clone's status or visibility
  (verified — no `is_internal` coverage in the sale/purchase suites).
- **Medium risk (guard against):**
  - `Product.status` changes affect `validate_active` (blocks SOLD/DEAD/CONSUMED products
    from new ops), product detail, period valuation, and Fix 8 reversal semantics. The
    transfer-in/out status resolution must be scoped so normal SOLD/DEAD/CONSUMED behavior
    is unchanged.
  - `stock_detail` "live" semantics change; the quick-consume test and the stock-detail
    rework plan must stay compatible.
  - `ProductLedgerEntry` idempotency keys must cover the new entry types so re-runs are safe.
- **High-care:**
  - The Fix 1 ownership guard must not be weakened globally; only internal-transfer clones
    get the scoped exception.
  - Reversal must not double-count: reversing a sale must remove the buyer clone, reversing
    a purchase must restore the vendor's stock.

## Out of scope / decisions needed

- **Physical Stock Transfer operation** stays deferred (per Fix 7 user decision); the
  sale/purchase clone remains the intra-farm transfer mechanism.
- **Question for user:** is the buyer clone allowed to be used in further operations
  (sold/dead/consumed) after an internal sale, i.e. should it behave as real ACTIVE stock?
  This determines whether we treat transfer-in clones as fully "live" stock or as a
  read-only view of transferred goods.
