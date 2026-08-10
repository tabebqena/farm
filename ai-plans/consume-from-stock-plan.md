# Plan — One-Step "Consume from Stock"

**Status:** Implemented — 2026-08-10.
**Date:** 2026-08-10
**Parent:** [`ai-plans/consumption-vs-expense-analysis.md`](consumption-vs-expense-analysis.md) (deferred item).
**Scope:** `apps/app_inventory` (views, urls, templates), `apps/app_operation/models/proxies/op_consumption.py`, tests.

---

## 1. Goal

Remove the friction of daily feeding. Today consuming feed/medicine requires a separate **Consumption operation** (create op → add invoice item → select product → auto movement). For a farmer who feeds every day this is heavy, which pushes them toward the incorrect shortcut (recording feed as an Expense).

Target: **one action** — from stock detail, pick the product and a quantity, click "Consume" — and the ConsumptionOperation, its invoice item, auto movement line, and ledger entries are all created in one step.

---

## 2. Context

- The existing full flow is `ConsumptionOperation.create(...)` driven by a formset POST (`items-0-selected_product`, `quantity`, `unit_price`, …) — see [`test_consumption_consumption_create.py`](../apps/app_operation/tests/operations/inventory/test_consumption_consumption_create.py).
- Availability/ownership/unit guards already exist in [`InventoryMovementLine.clean()`](../apps/app_inventory/models.py:1241) and the auto-movement path.
- The stock detail page ([`stock_detail.html`](../apps/app_inventory/templates/app_inventory/stock_detail.html)) already lists the project's products with their ledger state.

---

## 3. Design

Add a **quick-consume** entry point on the stock/consumption pages that submits a minimal form to a new view. The view builds a single-item formset internally and calls the existing `ConsumptionOperation.create(...)` factory so all side-effects (issuance + payment transactions, auto movement line, `CONSUMPTION_MOVEMENT` ledger, product `CONSUMED`) reuse the proven path.

### Form fields (quick consume)
- `product_id` (hidden; the product being consumed)
- `quantity` (number input; step = `product_template.minimum_quantity`)
- `unit_price` (pre-filled with the product's carried `unit_price`, editable)
- `date` (default today) and optional `description`/`notes`

### Validation (reuse existing guards)
- Availability: `quantity ≤ ProductLedgerEntry.state_as_of(product, date)["quantity"]` — cannot consume more than physically on hand.
- Ownership: product belongs to the source project.
- Unit consistency: quantity is a multiple of `minimum_quantity`.

---

## 4. Implementation steps

1. **View** — add `quick_consume(request, entity_pk)` (or extend the existing consumption create view) in [`apps/app_inventory/views.py`](../apps/app_inventory/views.py):
   - Build `raw_post` for a single item formset, call `ConsumptionOperation.create(...)` with `source=project`, `destination=system`, `amount=quantity × unit_price`.
   - Redirect back to stock detail with a success/error message.
2. **URL** — add a route in [`apps/app_inventory/urls.py`](../apps/app_inventory/urls.py).
3. **Template** — add a small "Consume" button + inline quantity form on [`stock_detail.html`](../apps/app_inventory/templates/app_inventory/stock_detail.html) (and/or a "Consume from stock" action in the product detail / stock list).
4. **Reuse vs. extend** — prefer calling `ConsumptionOperation.create(...)` unchanged; only extend if the factory requires formset shape that the quick form can't provide.
5. **Tests** — `test_quick_consume_from_stock.py`:
   - One call creates the ConsumptionOperation, one movement line, `CONSUMPTION_ISSUANCE` + `CONSUMPTION_PAYMENT` transactions, `CONSUMPTION_MOVEMENT` ledger, and product status `CONSUMED`.
   - Over-consumption (qty > on-hand) raises ValidationError.
   - Partial consumption: remaining ledger qty equals on-hand − consumed.
6. **Spec** — note the quick path in [`op_19_consumption.md`](../specs/operations/op_19_consumption.md).

---

## 5. Verification

- `python manage.py test apps.app_inventory.tests apps.app_operation.tests.operations.inventory --parallel=4`
- `python manage.py check`

---

## 6. Implementation status

**Implemented 2026-08-10.**

- ✅ View: [`quick_consume()`](../apps/app_inventory/views.py) added in `apps/app_inventory` — POST-only; officer (`is_staff`) gate; ownership, nature (FEED/MEDICINE), availability (`ProductLedgerEntry.state_as_of`), and `minimum_quantity` multiple guards; builds the single-item formset `raw_post` and delegates to the unchanged `ConsumptionOperation.create(...)` factory; redirects back to stock detail with Django messages.
- ✅ URL: `entity/<int:entity_pk>/stock/consume/` (`name="quick_consume"`) in [`apps/app_inventory/urls.py`](../apps/app_inventory/urls.py).
- ✅ Template: "Consume" `<details>` + inline quantity/unit-price/date/description form added to both the table and card views of [`stock_detail.html`](../apps/app_inventory/templates/app_inventory/stock_detail.html); the full consumption form is still reachable via an "Advanced" link.
- ✅ Tests: [`test_quick_consume_from_stock.py`](../apps/app_inventory/tests/test_quick_consume_from_stock.py) — full pipeline (op, movement line, `CONSUMPTION_ISSUANCE` + `CONSUMPTION_PAYMENT`, `CONSUMPTION_MOVEMENT` ledger, product `CONSUMED`), partial consumption remainder, over-consumption rejection, officer gate, non-consumable nature rejection, and cross-entity product rejection.
- ✅ Spec: quick path documented in [`op_19_consumption.md`](../specs/operations/op_19_consumption.md).
- ✅ Verification: `manage.py test apps.app_inventory.tests apps.app_operation.tests.operations.inventory --parallel=8` (142 tests OK) and `manage.py check` (no issues).
