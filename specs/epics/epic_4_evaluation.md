# EPIC 4 — Evaluation System
> `app_evaluation` has a `ProductEvaluation` model referencing `Product` which doesn't exist.

---

### Feature 4.1 — Product Model
**Goal:** `ProductEvaluation` has a FK to `"Product"` that doesn't exist.

Tasks:
- [ ] Decide: does `Product` live in `app_inventory` (likely yes — it's a sellable/purchasable item)?
- [ ] Add `Product` model to `app_inventory` with fields: `name`, `category`, `default_unit`, `description`
- [ ] Update `ProductEvaluation.product` FK to point to `app_inventory.Product`
- [ ] Create and run migrations

---

### Feature 4.2 — Evaluation Flow
**Goal:** Evaluations record the assessed price of a product at a point in time. Wire it up.

Tasks:
- [ ] Add `evaluated_at` DateField to `ProductEvaluation`
- [ ] Add a view to create an evaluation for a product
- [ ] Show evaluation history on product detail page (latest first)
- [ ] The latest evaluation's price should be usable as `InvoiceItem.unit_price` default
