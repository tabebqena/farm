# Fix the SALE Mechanism (sale-only plan)

**Status:** analysis only (implementation deferred). Scope limited to **SALE** — the purchase /
internal-vendor fix and the SALE-blocking step are handled in
`internal-entity-transfer-stock-plan.md` and the mechanism review
`stock-products-movements-mechanism-review.md`.

**User decisions (2026-08-12):**
- Keep the **sale wizard** and make it **affect the already-present product** (the seller's
  existing stock) — no fresh-product minting.
- In the wizard, **select from the seller's existing products** instead of product templates
  (`/sale/invoice/select-template/` and `/sale/invoice/add-item/` currently pick a template)
  — this simplifies the flow.
- **Remove the other sale path** — the wizard becomes the only sale UI.

## 1. Problem (verified)

The sale wizard path
([`SaleOperation.create_from_session()`](../apps/app_operation/models/proxies/op_sale.py:96)
← `sale_submit` ← `sale_invoice` ← [`sale_add_item_view`](../apps/app_operation/views/create_operation/sale_wizard.py:350))
currently:
1. **Selects a product template** (`sale_select_template_view` → `ProductTemplate`) and enters
   template/qty/price/tag/delivered_qty (`SaleItemForm`) — **not the existing products**.
2. **Mints fresh `SOLD` products** for the seller via
   [`create_products_for_item()`](../apps/app_inventory/models.py:895). Consequences:
   - The seller's **real on-hand stock is not reduced** — only paper `SOLD` rows appear; the
     actual goods stay `ACTIVE` in the seller's live stock.
   - Availability against real stock is **bypassed**
     ([`_validate_availability()`](../apps/app_inventory/models.py:1503) exempts
     sale-created products).
3. A **second, divergent sale path** exists ([`SaleCreateView`](../apps/app_operation/views/create_operation/create_sale_view.py:12)
   → `sale_form.html`, and the generic [`operation_create_view`](../apps/app_operation/urls.py:148))
   using [`InvoiceItemSelectFormSet`](../apps/app_inventory/forms.py:398).

This violates the principle: **a Product is the presence of something; movement lines affect
it.** A sale must select the seller's existing product and let the `SALE_MOVEMENT` line affect
it.

## 2. The fix

### 2.1 Sale wizard selects from existing products

Replace the template-selection item flow with **existing-product selection**:

- **`sale_select_template_view`** → becomes a "select product from stock" list: the seller's
  on-hand (`ACTIVE`, ledger-present) products of the project, shown with template name, tag
  (`unique_id`), quantity and available qty.
- **`sale_add_item_view` / `SaleItemForm`** → becomes a form that picks one (or several)
  existing product(s) from that stock (reuse the selection mechanics of
  [`InvoiceItemSelectForm`](../apps/app_inventory/forms.py:323), entity-filtered to the
  seller). The dispatch quantity comes from the selected product (optionally the user may
  enter the quantity to dispatch / the sale unit price).
- The session item now carries **product id(s)** (not `product_template_id`), so
  `create_from_session` knows exactly which existing products are being sold.
- This **simplifies the passes**: no separate template pick + item entry — the user picks the
  actual goods from stock in one step.

### 2.2 Movement lines affect the selected existing product

In [`SaleOperation.create_from_session()`](../apps/app_operation/models/proxies/op_sale.py:96):
- For each item, resolve the **selected existing product(s)** from session.
- **Availability guard (Fix 2):** the seller must physically hold the sold quantity — reject
  the sale atomically if not (no sale-created exemption since the product is existing).
- Create `SALE_MOVEMENT` line(s) against the selected product(s) (`product=` set explicitly —
  SALE never lazy-creates) and **link them to the invoice item**
  (`product.invoice_items.add(invoice_item)`) so `Product.status == SOLD` for a fully-sold
  product and the seller's live stock is reduced.
- **Remove** the `create_products_for_item` minting for the seller and the
  `if client.is_internal: create_products_for_item` clone block
  ([`op_sale.py`](../apps/app_operation/models/proxies/op_sale.py:187)) — the internal-client
  clone is superseded by the SALE-blocking step in the companion plan.

### 2.3 Remove the other sale path

- Delete [`SaleCreateView`](../apps/app_operation/views/create_operation/create_sale_view.py)
  and `templates/app_operation/sale_form.html`.
- Remove the `sale_create_view` route ([`urls.py`](../apps/app_operation/urls.py:142)).
- Exclude SALE from the generic [`OperationCreateView`](../apps/app_operation/views/create_operation/base.py:75)
  (`operation_create_view`) so no other sale entry point remains; the sale wizard
  (`sale_wizard_step1` → `sale_invoice` → `sale_submit`) is the only sale UI.
- Update navigation/menus that link to `sale_create_view` to point at `sale_wizard_step1`.

## 3. Behavior after the fix (external client — the only sale case)

| Item | Before | After |
|---|---|---|
| Wizard selection | product template + qty | seller's **existing** products from stock |
| Seller product | fresh `SOLD` row minted (real stock untouched) | seller's **existing** product reduced / marked `SOLD` |
| Seller live stock | real goods still `ACTIVE` | real goods leave live stock (movement net ≤ 0) |
| Availability | bypassed | enforced against on-hand |
| Ledger | `SALE_MOVEMENT` against fresh product | `SALE_MOVEMENT` against the real product |
| Internal-client sale | broken clone | (handled by SALE-blocking in companion plan) |

## 4. Files

| File | Change |
|---|---|
| [`apps/app_operation/models/proxies/op_sale.py`](../apps/app_operation/models/proxies/op_sale.py:96) | `create_from_session`: resolve selected existing products, create `SALE_MOVEMENT` against them, link to invoice items; remove minting + clone block |
| [`apps/app_operation/views/create_operation/sale_wizard.py`](../apps/app_operation/views/create_operation/sale_wizard.py) | `sale_select_template_view` → select existing product(s); `sale_add_item_view`/`SaleItemForm` → pick existing product(s); session stores product id(s) |
| [`apps/app_operation/forms.py`](../apps/app_operation/forms.py:262) | replace `SaleItemForm` with an existing-product selection form (reuse `InvoiceItemSelectForm` mechanics, entity-filtered to the seller) |
| `apps/app_operation/templates/app_operation/sale_select_template.html`, `sale_add_item`-related template | rework to list/pick the seller's on-hand products |
| [`apps/app_inventory/models.py`](../apps/app_inventory/models.py:1503) | ensure `_validate_availability` applies to the selected existing product |
| [`apps/app_operation/views/create_operation/create_sale_view.py`](../apps/app_operation/views/create_operation/create_sale_view.py) | remove (delete) |
| `apps/app_operation/templates/app_operation/sale_form.html` | remove |
| [`apps/app_operation/urls.py`](../apps/app_operation/urls.py:142) | remove `sale_create_view`; keep only wizard routes |
| [`apps/app_operation/views/create_operation/base.py`](../apps/app_operation/views/create_operation/base.py:75) | exclude SALE from generic create view |

## 5. Tests

- Wizard lists only the seller's on-hand products (no other project's stock).
- Selecting an existing INDIVIDUAL product → that product is `SOLD`, out of the seller's live
  stock, with a `SALE_MOVEMENT −1` ledger row; no new product is created.
- Selecting a COMMODITY product → the seller's existing product quantity is reduced by the
  sold qty; fully-sold → `SOLD`.
- Over-selling (qty > on-hand) → rejected (availability).
- Partial dispatch (`delivered_qty < quantity`) → the product's physical presence reflects the
  delivered qty.
- Reversal of a sale → the existing product returns to `ACTIVE`, movement negated (Fix 8).
- Wizard submit still creates the operation, issuance transaction, and (if paid) collection.
- Update/remove tests that relied on template-based selection, fresh-minted sale products, or
  the removed `sale_create_view` route.

## 6. Regression

- Sale tests that assert issuance/payment/SOLD status remain green; stock-side assertions are
  added.
- Removing the second sale path must not break menus or tests referencing `sale_create_view`
  (audit navigation + `test_views_*`).
- No ledger schema change; no migration.

## 7. Verify

- `python manage.py check`
- `pytest apps/app_operation/tests/operations/sale apps/app_inventory`
- Full suite: `manage.py test --parallel=8`

---

## 8. Implementation status (2026-08-12)

Implemented and verified — full suite green (1434 tests OK).

- **Wizard selects existing products:** `sale_select_template_view` → `sale_select_product_view`
  lists the seller's on-hand products (ledger-present, `ACTIVE`); `sale_add_item_view` +
  `SaleItemForm` now pick an existing product (`product_id`) with quantity/price; session
  items store `product_id`; `sale_invoice_view` displays the selected product/tag.
- **`SaleOperation.create_from_session()`** resolves the selected existing products, validates
  ownership + availability (`ProductLedgerEntry.state_as_of`), links them to the invoice item,
  and records a `SALE_MOVEMENT` line against them — **no fresh products are minted** and the
  internal-client clone block was removed.
- **Other sale path removed:** `SaleCreateView`, `sale_form.html`, `sale_create_view` route and
  `create_sale_view.py` deleted; the generic `OperationCreateView` now redirects SALE to the
  sale wizard; the operation-list Sale link points to `sale_wizard_step1`.
- **Tests:** new `test_sale_sale_create_from_session.py` (6 tests: existing-product affected,
  no mint, full disposal, INDIVIDUAL animal, over-sell atomic rejection, ownership rejection,
  issuance tx). Updated `test_views_get_operation_create_view.py` (sale redirects to wizard).
- **Known:** the previously stale `test_step1_no_clients_shows_error` (asserts a removed
  no-clients redirect) was commented out by the user.
- **Recheck (deferred to companion plans):** `Product.status` is still per-product (a partial
  commodity sale marks the whole product `SOLD`); the internal-vendor purchase fix and
  internal-sale blocking remain in `internal-entity-transfer-stock-plan.md`.
