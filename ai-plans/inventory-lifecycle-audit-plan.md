# Inventory / Operations Lifecycle — Hidden-Logic Audit & Fix Plan

**Date:** 2026-08-12
**Status:** Analysis complete — code changes deferred pending design decisions (see "Open decisions").
**Method (per user):** Do NOT treat the test suite as the source of truth — tests can verify an error. Each
finding is checked against the **expected logic** (domain semantics + `specs/operations/operations-comparison.md`
and the per-operation specs). Only divergences from the expected logic are reported.

---

## 1. The expected lifecycle (source of truth)

A **Product** is a physical asset owned by an entity. `InventoryMovementLine` records the physical events
(receipt / dispatch). `InvoiceItem` records the paper obligation. The expected lifecycle:

| Event | Effect on the seller / source entity | Status | Movement |
|---|---|---|---|
| PURCHASE | goods enter stock (lazily at movement) | ACTIVE | user-driven / deferred receipt |
| BIRTH | newborn enters stock (lazily at movement) | ACTIVE | auto inbound |
| SALE | goods **leave** the seller's stock | SOLD (or ACTIVE if partial) | must affect the seller's existing product |
| DEATH | asset written off | DEAD | auto outbound |
| CONSUMPTION | asset written off | CONSUMED | auto outbound |
| CAPITAL GAIN/LOSS | value-only | ACTIVE (unchanged) | none |

**Reversal semantics (expected):**
- Reversing an outbound op (SALE/DEATH/CONSUMPTION) restores the product to ACTIVE, and is **blocked** if the
  product was moved again downstream.
- Reversing an inbound op (BIRTH/PURCHASE) must **remove the created product from stock** — the asset should not
  linger as a phantom row (ACTIVE/REMOVED/SOLD) with zero or negative presence.
- A sale must **never** leave the seller's original product untouched while a new "sold" row appears.

**Invariant (expected):** a product is in stock **iff** its net active movement presence > 0; status, physical
presence, and the UI must all agree about whether a product exists / is in stock / is disposed.

---

## 2. Confirmed hidden issues (each verified against expected logic)

### H1 — `Product.is_physically_moved` is not reversal-aware (contradicts `status`)
- **Expected:** after every movement of a product is reversed, it is no longer "physically moved".
- **Actual:** [`Product.is_physically_moved()`](apps/app_inventory/models.py:588) returns `True` whenever any
  `reversal_of__isnull=True` line exists — reversed **originals** still count. The code's own comment at
  [`models.py:594`](apps/app_inventory/models.py:594) flags this as a known gap.
- **Impact:** a reversed-birth product reports `is_physically_moved=True` while `status` is REMOVED → UI shows
  "Physically Moved" for a removed asset; the SALE availability exemption at
  [`models.py:1073`](apps/app_inventory/models.py:1073) keys off this broken flag; `current_value`
  ([`models.py:756`](apps/app_inventory/models.py:756)) is gated by it.
- **Root cause:** the "which lines are active (not reversed)" predicate is reimplemented ~8 times with subtly
  different rules; `is_physically_moved` uses the wrong variant.

### H2 — Reversing a BIRTH (or PURCHASE) is not guarded against downstream disposal
- **Expected:** mirroring SALE/DEATH/CONSUMPTION, an inbound operation must not be reversible if its product was
  later disposed of — otherwise the asset can go **negative**.
- **Actual:** the reversal dependency guard in
  [`Operation.reverse()`](apps/app_operation/models/operation.py:1019) only covers DEATH/CONSUMPTION/SALE.
  A BIRTH auto-reverses its inbound lines with no check. Concrete sequence: born animal → later SOLD → reverse the
  BIRTH → the +1 inbound is negated, the SALE −1 remains → product has **net −1 presence**, status SOLD, and the
  SALE still looks valid.
- **Impact:** negative stock / phantom disposed assets — a data-integrity violation that no test exercises end-to-end.

### H3 — Purchase reversal leaves a phantom ACTIVE product (asymmetric with Birth)
- **Expected:** like birth, a product whose only entry into stock was a (now reversed) purchase no longer belongs in
  stock.
- **Actual:** the REMOVED fallback in [`_status_from_linked_operations()`](apps/app_inventory/models.py:720)
  special-cases **BIRTH only** (`operation__operation_type=OperationType.BIRTH`). A fully-reversed PURCHASE product
  falls through to `return ACTIVE` at [`models.py:728`](apps/app_inventory/models.py:728) — a phantom ACTIVE row
  with no movement presence.
- **Impact:** birth reversal → REMOVED zombie; purchase reversal → ACTIVE zombie. The two inbound operations are
  handled **inconsistently** — the clearest evidence of "fixes applied over errors instead of one lifecycle".

### H4 — Sale effect is enforced only in the wizard, not at the model layer
- **Expected:** a sale reduces the seller's stock; the seller's original product must be affected (SOLD / reduced).
- **Actual:** the wizard [`create_from_session()`](apps/app_operation/models/proxies/op_sale.py:96) does this
  correctly, but [`save_inventory()`](apps/app_operation/models/operation.py:803) does **nothing** for SALE, and
  [`Operation.create()`](apps/app_operation/models/operation.py:344) creates invoice items with **no movement
  lines**. A SALE created through the generic/programmatic path leaves the seller's product ACTIVE and the goods in
  stock — the "sale leaves the original project active" symptom is still latent in the model layer.
- **Impact:** the invariant "a sale must affect stock" is not enforced anywhere in the model; it only holds by
  convention in one view flow.

### H5 — Legacy SALE availability exemption is now dead / wrong code
- **Expected:** availability is enforced against the seller's real on-hand stock.
- **Actual:** [`_validate_availability()`](apps/app_inventory/models.py:1073) exempts "SALE products created at
  sale time (never received)" — a relic of the removed product-minting sale path. Because H1 makes
  `is_physically_moved` unreliable, this exemption can fire on the wrong products. The exemption has no valid
  caller left.

### H6 — Multiple divergent reimplementations of "active movement lines"
- **Expected:** one canonical definition of which lines are physically active (non-reversal, not reversed).
- **Actual:** independently re-implemented in [`active_movements()`](apps/app_inventory/stock.py:31),
  [`active_lines_for_item()`](apps/app_inventory/stock.py:51), [`_item_moved_qty()`](apps/app_inventory/stock.py:155),
  [`Product.status()`](apps/app_inventory/models.py:636), [`Product.is_physically_moved()`](apps/app_inventory/models.py:588),
  [`get_items_data()`](apps/app_operation/models/operation.py:719), [`build_movement_json()`](apps/app_inventory/models.py:485),
  and the stock view ([`views.py:71`](apps/app_inventory/views.py:71)). Each has its own filter; H1 is a direct
  consequence of the divergence.

### H7 — Sale/Death/Consumption reversal guard checks only outbound downstream ops
- **Expected:** reversing an outbound op should be blocked if the product was subsequently disposed (SALE/DEATH/
  CONSUMPTION) — already implemented — but also if a BIRTH/PURCHASE behind it is the only stock entry (see H2/H3).
- **Actual:** the guard at [`operation.py:1039`](apps/app_operation/models/operation.py:1039) only looks at
  `operation__operation_type__in=[SALE, DEATH, CONSUMPTION]`, so a sale can be reversed on a product whose inbound
  was already reversed → the product goes negative. The guard is not complete without H2/H3.

---

## 3. Deep root cause

There is **no single authoritative lifecycle state for a Product**. "Does it exist? Is it in stock? Is it
sold/dead/consumed/removed?" is answered by:

1. a derived `status` property with three fallbacks (movement-based → linked-operation → a BIRTH-only REMOVED case),
2. a separate `is_physically_moved` flag using a **different** active-lines rule,
3. ~8 independent re-implementations of the active-lines predicate,
4. per-operation-type guards and exemptions layered on top.

Because the lifecycle is derived and patched rather than stored-and-guarded, the same physical reality is
represented inconsistently across operation types (BIRTH→REMOVED vs PURCHASE→ACTIVE zombie) and across code paths
(wizard vs generic create). The tests were written to lock in each patched behavior, which is why they "verify the
error."

---

## 4. Proposed fix direction (structure only — details pending decisions)

### 4.1 Single source of truth
- Add **one** canonical helper, e.g. `active_movements_for(product, as_of)` (or a `Product.active_lines` queryset),
  that excludes reversal lines **and** reversed originals.
- Replace all ~8 reimplementations (H6) with it.
- Make `Product.is_physically_moved` use the same helper (fix H1) and remove the flagged TODO.

### 4.2 One lifecycle model for inbound reversal (fix H2, H3, H7)
- Add the reversal dependency guard for **BIRTH** (and the corresponding inbound leg for PURCHASE): block reversal
  if the product has any later non-reversed outbound movement (SALE/DEATH/CONSUMPTION).
- Decide (open decision) whether a reversed inbound leaves a `REMOVED` product or is hard-removed — and make the
  choice **identical** for BIRTH and PURCHASE, so status/stock/UI agree.

### 4.3 Model-level sale invariant (fix H4, H5)
- Enforce at the model layer that a non-reversal SALE must affect the seller's product via movement lines (reject a
  sale with no movement, or require it before the sale is considered complete).
- Remove the dead sale-created-product availability exemption (H5).

### 4.4 Invariant tests (not behavior tests)
- net active presence > 0 ⟺ in stock (across every op and reversal);
- `is_physically_moved` is reversal-aware;
- BIRTH reversal with a downstream SALE/DEATH/CONSUMPTION is blocked (negative-stock guard);
- PURCHASE reversal removes the product from stock identically to BIRTH;
- a SALE with no movement line is rejected at the model layer.

### 4.5 Docs
- Update `specs/operations/op_17_birth.md`, `op_13_purchase.md`, `op_14_sale.md` and
  `operations-comparison.md` to the chosen lifecycle; note what was implemented at the end of this file (per repo
  rules).

---

## 5. Open decisions (to discuss with the user before implementation)

1. **Birth/Purchase reversal lifecycle:** hard-remove the created product vs keep a consistent `REMOVED` state.
   - Hard-remove: cleanest inventory (no zombie rows), but loses the audit/product record and needs deletion
     handling (Product is FK-guarded by movement lines with PROTECT).
   - REMOVED: keeps audit, but every view/query/flag must consistently exclude REMOVED products; the UI must never
     show them as present.
2. **Sale invariant:** reject a sale that has no movement line at the model layer, or auto-create the movement
   during `create_from_session` only (and document that the generic path must not be used for SALE)?
3. **Scope of this pass:** fix only the inventory/lifecycle cluster above, or also run the same
   expected-vs-implementation audit over the financial operations (loan/repayment, expense, adjustments)?

---

## 6. Implementation status

Not yet implemented — awaiting the design decisions above.
