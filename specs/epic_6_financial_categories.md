# EPIC 6 — Financial Categories

---

### Feature 6.1 — Bulk Category Creation
**Goal:** `category_bilk_create.py` (note: typo in filename) exists but likely has issues.

Tasks:
- [*] Rename `category_bilk_create.py` → `category_bulk_create.py` and update imports in `__init__.py`
- [ ] Test the bulk create flow end-to-end: submit the form → categories appear in list
- [ ] Seed the default categories from `category.py`'s `default_categories` dict via a management command

---

### Feature 6.2 — Category Budget Enforcement
**Goal:** `FinancialCategory.max_limit` exists but is never enforced anywhere.

Tasks:
- [ ] Add a method `category.total_spent()` that sums all paid operation amounts in that category
- [ ] Add a method `category.remaining_budget()`
- [ ] Show remaining budget on `category_detail.html`
- [ ] Warn (but don't block) when an operation would exceed the category limit
