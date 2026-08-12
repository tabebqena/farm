# Inventory App — Complexity Review & Simplification Direction

**Status:** analysis (implementation deferred until scope confirmed).

## 1. The two questions the inventory app must answer

1. **Available for an entity** — which products are physically present, the quantity, and the
   value.
2. **Inbound / Outbound** — which movements brought goods in / sent them out (history).

Everything else in the app is supporting machinery. Today that machinery is large and partly
redundant.

## 2. Current model map (verified)

| Model | Role | Notes |
|---|---|---|
| `ProductTemplate` | catalog of product types (nature, tracking mode, unit, tag prefix) | nature→tracking, `entities` assignment, `next_tag` |
| `InvoiceItem` | contract line (what was ordered/sold) | `adjusted_*` from adjustments |
| `Product` | physical presence (entity, template, qty, tag) | derived `status`, `validate_active`, `is_physically_moved`, `current_value` |
| `InventoryMovementLine` | the physical event (operation, item, product, qty, date) | lazy creation, ownership/availability/unit guards, reversal |
| `ProductLedgerEntry` | append-only ledger (16 entry types) | issuances + movements + adjustments + value-only + reversal |
| `MedicalRecord` | animal health (vaccination/checkup/…) | **not an inventory concern** |

The two questions map to:
- **Q1 (available/qty/value)** → `ProductLedgerEntry.portfolio_as_of` + `stock_detail` (which
  combines a movement-based `net_qty` annotation AND the ledger portfolio).
- **Q2 (in/out)** → `stock_history` (movement lines with a direction label).

## 3. Where the complexity (and redundancy) lives

### 3.1 Two parallel records of the same physical reality
`InventoryMovementLine` (the event) is **written twice**: once as the line, once as a
`ProductLedgerEntry` "movement" row (idempotent via `idempotency_key`). This requires every
write to stay consistent, and drove most of the recent direction-aware changes (sign per
ownership side) in BOTH places.

The ledger also duplicates data that lives elsewhere:
- **movement entries** ← derivable from `InventoryMovementLine`
- **issuance entries** (PURCHASE_ISSUANCE, …) ← derivable from `InvoiceItem` (quantity/price)
- **adjustment entries** ← derivable from `InvoiceItemAdjustmentLine` (in `app_adjustment`)
- only **CAPITAL_GAIN / CAPITAL_LOSS** (value-only) are ledger-native

So `ProductLedgerEntry` is effectively a **materialized query layer**. The single source of
truth for physical quantity is the movement lines.

### 3.2 Two valuation implementations that can drift
- [`Product.current_value`](../apps/app_inventory/models.py:1207) = `unit_price × quantity` +
  capital gains/losses (computed from invoice items).
- [`ProductLedgerEntry.inventory_value_at`](../apps/app_inventory/models.py:422) = summed
  ledger `value_delta`.
- [`app_operation.period`](../apps/app_operation/models/period.py:327) consumes the ledger for
  period inventory value → cross-app coupling to the ledger.

### 3.3 `Product.status` is a redundant label
`status` is derived from the linked operations (`invoice_items`), now direction-aware. But
physical presence is already computed from movement lines/ledger. The status drives
`validate_active` (can the product be used again). It adds coupling Product ↔ Operation and
per-product (not per-quantity) semantics — the source of the "partial commodity sale marks the
whole product SOLD" limitation.

### 3.4 Non-inventory content
`MedicalRecord` (animal health) lives in the inventory app — a separate domain.

### 3.5 Template assignment overhead
`ProductTemplate.entities` — a template must be assigned to an entity to be used; adds config
and recently required a `portfolio_as_of` ownership fix.

### 3.6 The `stock_detail` page is heavy
Search + pagination + a direction-aware SQL `net_qty` annotation AND a ledger portfolio —
several mechanisms to answer "what's available".

## 4. Simplification direction (anchor on the two questions)

### Q1 — Available (portfolio)
**Source of truth = `InventoryMovementLine`.** A portfolio is: for an entity, sum active
(non-reversal) movement deltas per product, direction-aware (source-owned SALE = in; else out).
Value = quantity × carried cost. This can be a single query over movement lines — no separate
ledger table needed for physical quantity/value.

### Q2 — Inbound / Outbound (history)
**`InventoryMovementLine`** filtered by entity/product with the direction label (already
implemented in `stock_history`). Keep it as the single history view.

### Proposed phases

**Phase A — low risk, reorganize (no data model change):**
- Move `MedicalRecord` out of the inventory app (animal-health domain).
- Reconcile `Product.current_value` with the ledger valuation (one valuation helper), so
  `app_operation.period` and inventory agree.
- Decouple `Product.status` from operations → derive from physical presence / movement
  direction (resolves the partial-sale status limitation too).
- Keep `stock_detail` (available) + `stock_history` (in/out) as the two clean pages.

**Phase B — medium risk, single source of truth:**
- Drop the movement rows from `ProductLedgerEntry` (or the whole ledger) and compute
  available/value directly from `InventoryMovementLine` + `InvoiceItem` + adjustments.
- Migrate `portfolio_as_of`, `inventory_value_at`, `pending_items` to the new sources.
- Keep idempotency by enforcing one active movement line per (operation, invoice_item, product)
  rather than a duplicate ledger row.

**Phase C — scope the contract/obligation layer:**
- Decide whether "pending / obligated" (ordered but not received) is a core requirement; if not,
  drop `pending_items`/`pending_deliveries` and the `is_obligated_only` machinery.
- Simplify `ProductTemplate` (drop `entities` assignment or make it a pure catalog).

## 5. Trade-offs / risks

- **Phase B removes the idempotency safety net** of the ledger — must be replaced with a unique
  constraint on movement lines and careful reversal handling.
- **Phase B changes `app_operation.period` valuation** — must keep the period's
  `inventory_value_*` output identical (verified by period tests).
- `Product.status` decoupling affects `validate_active`, product detail, and stock views — scope
  carefully with tests (external flows unchanged).

## 6. Decisions (2026-08-12) and new direction

1. **Drop `ProductLedgerEntry`.** Available/qty/value and obligations are computed from
   `InventoryMovementLine` (+ `InvoiceItem` for contract), not from a duplicate ledger.
2. **Keep `pending_items` / `pending_deliveries`** (the contract/obligation layer) but **postpone
   and compute them from another place** (movement lines vs. `InvoiceItem` quantities) — no
   ledger dependency.
3. **Discussing: remove `Product.entity`** and derive a product's ownership from its movement
   lines (a movement-line owner / last-status concept). Vision: a product is **created once**
   (birth or purchase from an external entity), then **tracked** (its value, quantity and status
   change via movements) until it leaves (consumption, death, sale).

## 7. Discussion — removing `Product.entity` and deriving ownership from movements

### 7.1 The vision
One persistent `Product` per physical item (or lot), created once on birth/purchase. Its owner,
quantity, value and status are derived from the movement lines that touch it. An internal
transfer is just an **ownership change via a movement** — no clone. External exit
(consumption/death/sale) marks it gone/terminal.

### 7.2 What it simplifies
- **No clones.** An internal-client sale moves the SAME product to the buyer (owner change)
  instead of minting a buyer copy. This removes the clone machinery added for internal transfers.
- `Product` becomes a thin identity (template, tag, current qty/value/status) rather than an
  entity-owned row.
- Ownership is a single derived concept (from movements), not a duplicated FK that must be kept
  in sync with movement directions.
- `Product.entity` currently drives stock views, ownership guards, portfolio and status — all of
  which become ownership-derived.

### 7.3 The key complication — COMMODITY partial transfers
- **INDIVIDUAL (animals):** clean — one product, one owner at a time; a movement transfers
  ownership.
- **COMMODITY (feed/medicine):** a lot is one product. Selling part of it cannot give "one
  product" two owners. Options:
  - **(a) Split:** the sold portion becomes a NEW product (owner = buyer), the retained portion
    stays on the original (owner = seller). Adds an explicit **split** operation.
  - **(b) Owner-tagged aggregation:** drop `Product.quantity` and derive qty/value per owner from
    movement lines carrying an `owner`. Then a commodity can be split across owners
    simultaneously, and "available for entity" = sum of owner-tagged deltas. Cleaner for
    commodities but reintroduces ownership-aware aggregation (the thing clones solved).
- Recommend **(a) split** — keeps "one product = one owner" simple and is the standard
  inventory model; the split is explicit and testable.

### 7.4 Status on the movement line
Storing the **last status** on a movement line (or deriving it from the last movement type) is
reasonable — it replaces `Product.status` derived from `invoice_items`, and removes the
Product↔Operation coupling (and the partial-sale per-product limitation: status would be
per-product still, but derived from movements rather than operations).

### 7.5 Implementation cost / risk (honest)
Removing `Product.entity` is a **large migration**: it is used by stock views, ownership guards,
`portfolio_as_of`, direction-aware status/stock_detail, sale preselection, purchase lazy
creation, period valuation and many tests. Ownership resolution adds a query (current owner =
last non-reversal owner-tagged movement), and commodity partial transfer needs the split.
This is conceptually simpler but implementation-heavy — recommend a dedicated phased plan with
a data migration + full test overhaul.

## 8. Root cause: one `Product` model for fundamentally different kinds

**User (2026-08-12):** "The deep issue arises from storing animals, medicine, feed & general
products in a general `Product` model."

This is the deepest source of complexity. One model tries to serve two different domains:

| Concern | Animal (INDIVIDUAL) | Feed/Medicine/Product (COMMODITY) |
|---|---|---|
| Identity | each animal is a distinct living entity | fungible lot (no individual identity) |
| Quantity | always 1 | lot size / weight |
| Extra fields | gender, birth_date, mother, health records, can die / give birth | unit, lot |
| Status semantics | per-animal (alive/dead/sold) | per-lot (on-hand / consumed / sold) |
| Exit ops | sale, death | sale, consumption |
| Entry ops | birth, purchase | purchase |

The single `Product` model forces this split into **branching everywhere**:
- `ProductTemplate.tracking_mode` (INDIVIDUAL vs COMMODITY) and nature-derived branching.
- `Product.quantity` meaning "1 animal" vs "lot size".
- Per-product (not per-quantity) status — the partial-commodity-sale limitation.
- Animal-only fields (`gender`, `birth_date`, `mother`, `MedicalRecord`) present on every row.
- `create_products_for_item` / movement lazy-creation branching on tracking mode.
- `unique_id` tag meaningful only for animals, optional for commodities.

**Proposed model separation:**
- `ProductTemplate` stays as the shared **catalog** (nature → concrete type, unit, tag prefix).
- **`Animal`** — individual: `gender`, `birth_date`, `mother`, `MedicalRecord`; qty implicitly 1;
  lifecycle born → (transferred) → died/sold.
- **`Commodity`** — fungible lot: quantity + unit; lifecycle received → (transferred) →
  consumed/sold.
- A shared abstract base (`StockItem`) holds the common fields (template, tag, carried cost,
  movement history). `InventoryMovementLine`/`InvoiceItem` reference the base.

This removes the tracking-mode branching, the quantity ambiguity, and the status-per-product
problem. It is a **structural data-model refactor** (migration + test overhaul), but it
directly addresses the root cause and simplifies the ownership/status/available questions
discussed above.

**Modeling choices to decide (Django):**
- **Multi-table inheritance** (`StockItem` parent + `Animal`/`Commodity` children): one FK to the
  parent; clean polymorphism; query joins on every access.
- **Concrete tables + GenericForeignKey** on movement/invoice: no parent table; loses join
  efficiency and FK integrity.
- **Two FKs** (animal / commodity) on movement lines: explicit but ugly and double-writes.

## 9. Open questions

- Confirm the **Animal / Commodity split** as the target model (root-cause fix).
- Which Django modeling approach (multi-table inheritance / GenericFK / two-FK)?
- Commodity partial transfer: **split** vs owner-tagged aggregation?
- Keep `StockItem` with stored current qty/value/status (updated by movements) vs fully derived?
- Where should animal-health records (`MedicalRecord`) live?
- Implementation sequence: Phase A (reorganize) → drop ledger → model split — or split first?
