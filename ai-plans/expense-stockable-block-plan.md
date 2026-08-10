# Plan — Hard Block: `FEED`/`MEDICINE` Cannot Be Recorded as Expense

**Status:** Rejected / superseded — **no code change**. Decision recorded 2026-08-10: keep the existing guidance-only note.
**Date:** 2026-08-10
**Parent:** [`ai-plans/consumption-vs-expense-analysis.md`](consumption-vs-expense-analysis.md) (deferred item).
**Scope:** *None — no code changes required.* (Original proposal touched `apps/app_operation/models/operation.py`, `apps/app_operation/models/proxies/op_expense.py`, `apps/app_inventory/models.py`, Expense form/templates, migration, tests.)

---

## 1. Goal

Turn the current **guidance-only** boundary (a note on the Expense form) into a **model-enforced block**: a stockable input (`FEED`/`MEDICINE` template) cannot be recorded as a plain Expense — it must go through Purchase + Consumption so it stays tracked in inventory and valued until used.

---

## 2. Context / challenge

- An Expense ([`ExpenseOperation`](../apps/app_operation/models/proxies/op_expense.py)) is `project → world`, `has_invoice=False`, category-required — it has **no link to any ProductTemplate**, so today the system cannot tell whether an expense "is feed".
- The correct behavior per the approved hybrid decision: stockable consumables belong in inventory (Purchase + Consumption); Expense is only for non-stocked / immaterial items.
- The boundary therefore needs an explicit, optional link from the Expense to a stockable item so the model can enforce it.

---

## 3. Design

### Option A — optional `stockable_item` link on Expense (recommended)
Add a nullable FK from `Operation` to `ProductTemplate` named e.g. `stockable_item` (`related_name="expense_items"`), shown only on Expense create.

- On the Expense form, an optional dropdown "Related stockable item (if any)" lists the entity's `FEED`/`MEDICINE` templates.
- Model-level check in [`Operation.clean()`](../apps/app_operation/models/operation.py:490) (or `ExpenseOperation.clean()`): if `category_required` and `self.stockable_item_id` is set **and** `stockable_item.nature in (FEED, MEDICINE)` → raise `ValidationError`:
  > "Feed/medicine are stockable inputs. Record them with Purchase + Consumption so they stay in inventory; use Expense only for non-stocked items."

- ✅ Real, model-enforced block; optional (a genuine non-stocked expense still works without selecting an item).
- ❌ One migration; a new field on the shared `Operation` table (or a dedicated one-to-one on Expense via a separate model).

### Option B — dedicated `ExpenseItemType` classification
Introduce a small `ExpenseItemType` model (or reuse `FinancialCategory`) whose set is explicitly **non-stockable**; any attempt to create an Expense that maps to a `FEED`/`MEDICINE` template is rejected.
- ✅ Cleaner separation.
- ❌ More new models/UI; overlaps with existing `FinancialCategory`.

### Option C — name/heuristic match (not recommended)
Block expense categories or descriptions whose text matches a `FEED`/`MEDICINE` template name.
- ❌ Fragile, brittle, localization-hostile.

**Recommendation:** Option A.

### Decision (2026-08-10) — no code change; keep guidance-only

Both enforcement options were re-evaluated and found **unnecessary**:

- **Option A (moot):** An Expense cannot reference a `ProductTemplate` at all — `ExpenseOperation.has_invoice = False` means no invoice items are ever created, the create form builds no item formset, and `Operation` has no FK to `ProductTemplate`. The forbidden state ("an expense carries a feed/medicine item") is **impossible by construction**, so adding a `stockable_item` link purely to block it is circular.
- **Option B (moot):** `FinancialCategory` is, by design, a classification of **non-stockable** expenses (services and immaterial supplies). All categories are unstockable, so an `is_stockable_input` flag would always be `False` and adds nothing — there is nothing to filter out of the Expense category dropdown.

**Conclusion:** The existing guidance note on the Expense form ([`category.html`](../apps/app_operation/templates/app_operation/snippets/create-form/category.html)) already communicates the rule ("Expense is for services and non-stocked supplies… use Purchase + Consumption for stockable inputs"). No model, view, template, migration, or test changes are made.

---

## 4. Implementation steps (Option A)

1. **Model** — add nullable `stockable_item = models.ForeignKey("app_inventory.ProductTemplate", null=True, blank=True, on_delete=models.PROTECT, related_name="operation_stockable_items")` to [`Operation`](../apps/app_operation/models/operation.py:34).
2. **Validation** — in [`Operation.clean()`](../apps/app_operation/models/operation.py:490), add: if `category_required` and `stockable_item_id` and `stockable_item.nature in (FEED, MEDICINE)` → raise `ValidationError` with guidance (Purchase + Consumption).
   - Keep the existing guidance note on the Expense form ([`category.html`](../apps/app_operation/templates/app_operation/snippets/create-form/category.html)).
3. **Form** — add the optional `stockable_item` dropdown to the Expense create form (populate from the entity's `FEED`/`MEDICINE` product templates). Wire it through `Operation.create(...)`.
4. **Migration** — `makemigrations app_operation` for the new FK.
5. **Tests**:
   - Creating an Expense with a `FEED` or `MEDICINE` `stockable_item` raises `ValidationError`.
   - Creating an Expense with `stockable_item=None` or a non-stockable reference succeeds.
   - Purchase + Consumption still work (no regression).
6. **Spec** — update [`op_12_expense.md`](../specs/operations/op_12_expense.md) with the new rule.

---

## 5. Verification

- `python manage.py test apps.app_operation.tests.operations.expense apps.app_operation.tests.operations.inventory --parallel=4`
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`

---

## 6. Implementation status

**2026-08-10 — DECISION: Not implemented.** Plan superseded — see §3 "Decision". No code changes made.

- [x] Confirmed an Expense cannot reference a `ProductTemplate` (Option A moot).
- [x] Confirmed all `FinancialCategory` records are inherently non-stockable (Option B moot).
- [ ] Model changes — N/A
- [ ] Migration — N/A
- [ ] Form/template changes — N/A
- [ ] Tests — N/A
- [ ] Spec update — N/A (existing guidance note retained)
