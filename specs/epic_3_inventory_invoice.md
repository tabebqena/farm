# EPIC 3 — Inventory & Invoice System
> `app_invoice` references `app_inventory.InventoryItem` which doesn't exist yet. This whole epic is new.

---

### Feature 3.1 — Inventory App Scaffold
**Goal:** Create `apps/app_inventory/` with the `InventoryItem` model that `Invoice` depends on.

Tasks:
- [ ] Create `apps/app_inventory/` with standard Django app structure
- [ ] Add `InventoryItem` model with fields: `name`, `unit` (kg/l/piece/etc.), `description`, `is_active`
- [ ] Add `apps.app_inventory` to `INSTALLED_APPS` in `settings.py`
- [ ] Create and run migrations
- [ ] Register in admin

---

### Feature 3.2 — Fix Invoice Model Imports
**Goal:** `app_invoice/models.py` imports from `app_base` without the `apps.` prefix, and references `Operation` directly instead of via `app_operation`.

Tasks:
- [ ] Fix `from app_base.models import BaseModel` → `from apps.app_base.models import BaseModel`
- [ ] Fix `models.ForeignKey("Operation", ...)` → `models.ForeignKey("app_operation.Operation", ...)`
- [ ] Run `python manage.py check` — should pass

---

### Feature 3.3 — Invoice Total Price
**Goal:** `Invoice.total_price` raises `NotImplementedError`. Implement it.

Tasks:
- [ ] Implement `Invoice.total_price` as sum of all `InvoiceItem.total_price` values
- [ ] Add `Invoice.item_count` property
- [ ] Add validation: invoice must have at least one item before it can be saved (or warn in template)
- [ ] Write unit test

---

### Feature 3.4 — Invoice UI on Operation Detail
**Goal:** Purchase and Sale operations show an `invoice_formset` snippet in the create form, but there's no detail view for viewing/editing an invoice after creation.

Tasks:
- [ ] Add `invoice_detail` URL and view (read-only first)
- [ ] Link to it from `operation_detail.html`
- [ ] Show: all line items, quantities, unit prices, total
