# Financial Categories — Entity Contract

**Epic:** Entity & Stakeholder Management — Relationships & Structure
**Area app:** `app_entity`
**Actions:** `assign (bulk)`, `activate`, `remove (deactivate)`, `save max_limit`, `link (wizard)`, `detail`
**Contract status:** v1 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **FinancialCategory** catalog and the **FinancialCategoriesEntitiesRelations** through model that links categories to entities with an optional per-entity `max_limit`, together with the category-relation views (`CategoryBulkAssignView`, `CategoryRelationEditView`, `CategoryRelationDetailView`) and the wizard's category step.
> Every clause below names its implementing code (model → consumer → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> The models live in `apps/app_entity/models/category.py`; the category FKs consumed by operations (`Operation.category` → `FinancialCategory`) make this area part of the operation engine — see `docs/operations`.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Catalog model | `FinancialCategory` — `name`, `description`, `aspect` | |
| Through model | `FinancialCategoriesEntitiesRelations` — `entity` FK (PROTECT, related `financial_categories_entities_relations`), `category` FK (PROTECT, related `entities_relations`), `max_limit` (Decimal(12,2), ≥ 0), `is_active` | |
| M2M surface | `FinancialCategory.entity` / `Entity.categories` (through the relation model) | |
| Uniqueness (live-only) | `unique_financial_category_name_live` (category name) · `unique_entity_category_relation_live` ((entity, category) pair) | |
| Soft-delete | category/relation rows are `BaseModel`; relations deactivated rather than deleted; auto soft-deleted with the owning entity (`Entity._delete_auto_relations` → `financial_categories_entities_relations`) | |
| Bulk assign view | `CategoryBulkAssignView` (`<parent_entity_id>/category/bulk-assign/` → `category_bulk_assign_view`) | |
| Relation edit view | `CategoryRelationEditView` (`category/edit/<int:pk>` → `category_relation_edit_view`) | |
| Relation detail view | `CategoryRelationDetailView` (`category/detail/<int:pk>` → `category_relation_detail_view`) | |
| Wizard category step | step 2 (select) + Summary linking (see [Project & Setup Wizard](entity_3_project.md)) | |

---

## 2. Registered business logic (contract map)

### 2.1 Model / domain layer

| Concern | Implementing code |
|---------|-------------------|
| `FinancialCategory` + `FinancialCategoriesEntitiesRelations` models | (`apps/app_entity/models/category.py`) |
| Live-only unique names + unique live (entity, category) pair | constraint definitions on both models |
| Category catalog seeding | `seed` command (`app_base`) default categories + `get_or_create` in test seeders |

### 2.2 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Bulk assign / remove for one entity | `CategoryBulkAssignView` |
| Relation actions (remove / activate / save max_limit) | `CategoryRelationEditView` |
| Relation detail + usage readout | `CategoryRelationDetailView` |
| Templates | `app_entity/category/category_bulk_form.html`, `app_entity/category/category_relation_edit_form.html`, `app_entity/category/category_relation_detail.html` |

### 2.3 Cross-app consumers

| Concern | Consumer |
|---------|----------|
| `Operation.category` FK → `FinancialCategory` | `Operation` model (`app_operation`) |
| Expense picks a category only when it is linked to the URL entity | operation create base (`has_category` → `FinancialCategory.objects.filter(entities_relations__entity=url_entity, …)`) |
| Category required at model + validator layers | `Operation.clean()` (when `has_category`) + `OperationDataValidator` (`has_category` branch) |
| Category recorded on an operation | Expense / adjustment create flows (see `docs/operations` op specs) |

### 2.4 Tests

| Concern | Test file |
|---------|-----------|
| Live-only category-name reuse | `app_entity.tests.test_soft_delete_unique_reuse` (`FinancialCategoryUniqueReuseTests`) |
| Live-only (entity, category) reuse | `app_entity.tests.test_soft_delete_unique_reuse` (`EntityCategoryRelationUniqueReuseTests`) |
| Wizard category step + linking/rollback | `app_entity.tests.test_project_setup_wizard_project_setup_wizard_step2` · `…_integration` |
| Category consumption by operations | `app_operation.tests` expense/correction/adjustment suites |

---

## 3. Domain model & invariants

- **Categories are a global catalog** (`name`, `aspect`); the app creates defaults through the `seed` command and links categories to entities through relations. There is no `app_entity` create/edit view for the catalog itself (no admin registration either) — the UI manages *relations*, not catalog rows.
- A category is **linked to an entity** through a `FinancialCategoriesEntitiesRelations` row carrying:
  - `max_limit` — an optional per-entity spending cap (Decimal, ≥ 0, default `0.00`), and
  - `is_active` — activation state (relations are activated/deactivated, never hard-deleted).
- **Live-only uniqueness.** Category `name` and the (entity, category) pair are unique **among live rows only**, so soft-deleted categories/relations free their names/pairs for reuse (matching the Entity rule).
- **PROTECT semantics.** Both FKs are `PROTECT`; a relation is a protected dependent of its entity and its category. Deleting an entity auto soft-deletes its relations (`Entity._delete_auto_relations`).
- **No spending enforcement yet.** `max_limit` is stored metadata; nothing in the operation engine enforces spending against it, and the relation-detail "usage %" readout is a placeholder (`usage_percentage` is hard-coded to `0`). Registered as a gap (§8).

---

## 4. Derived financial contract

`N/A` — category rows carry no balance. Their financial meaning is indirect: the `Operation.category` FK records which linked category an expense belongs to, and `max_limit` is the (unenforced) intended cap for that entity+category.

---

## 5. Actions

### 5.1 `bulk assign` — `CategoryBulkAssignView` (GET/POST `<parent_entity_id>/category/bulk-assign/`)

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CA1 | Entity exists + live | parent entity pk resolves | 404 (custom message) | `"Entity not found or has been deleted."` | `get_object_or_404` | no direct pinning test (gap) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CA2 | Selected categories activated/created | for each selected pk: `get_or_create(entity, category)` then `is_active=True` (created counted) | `_apply_bulk_assign` (atomic) | no direct pinning test (gap) |
| CA3 | Unselected linked categories deactivated | existing relation set `is_active=False` (removed counted) | `_apply_bulk_assign` | no direct pinning test (gap) |
| CA4 | Audit + message + redirect | `categories_bulk_assigned` audit, created/removed counts message (or warning when nothing changed), redirect `entity_detail` | `_bulk_assign_post` | no direct pinning test (gap) |
| CA5 | GET lists catalog + active selections | context `categories` (all) + `existing_category_names` (active relation pks) | `get()` | no direct pinning test (gap) |

### 5.2 `relation actions` — `CategoryRelationEditView` (GET/POST `category/edit/<int:pk>`)

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CR1 | Relation exists + live | pk resolves to a live relation | 404 (custom message) | `"Category assignment not found or has been deleted."` | `get_object_or_404` | no direct pinning test (gap) |
| CR2 | `max_limit` is valid Decimal ≥ 0 | `Decimal(raw)` parses and passes the model validator | `ValidationError` → error message + re-render | `"Update failed: …"` | `Decimal` + `MinValueValidator(0)` | no direct pinning test (gap) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CR3 | `remove` deactivates | `relation.is_active = False` (row kept for history) | `_apply_relation_action` (atomic) | no direct pinning test (gap) |
| CR4 | `activate` activates | `relation.is_active = True` | `_apply_relation_action` | no direct pinning test (gap) |
| CR5 | `save` updates `max_limit` only | `relation.max_limit = Decimal(raw)`; entity/category untouched | `_apply_relation_action` | no direct pinning test (gap) |
| CR6 | Audit + message + redirect | per-action audit verb, success message, redirect `entity_detail` (entity) | `_relation_audit` + `_relation_success_message` | no direct pinning test (gap) |

### 5.3 `relation detail` — `CategoryRelationDetailView` (GET `category/detail/<int:pk>`)

| # | Branch | Behavior | Enforced by | Pinned by test |
|---|--------|----------|-------------|----------------|
| CD1 | Load | live relation by pk, else 404 (message) | `get_object_or_404` | no direct pinning test (gap) |
| CD2 | Context | `category`, `parent`, `relation`, `usage_percentage` (currently **stub = 0**) | `CategoryRelationDetailView.get` | no direct pinning test (gap) |

### 5.4 `link` (wizard, step 2 / Summary)

Category linking is part of the [Project & Setup Wizard](entity_3_project.md) contract: step 2 stores selected category pks in the draft; the Summary create links each via `FinancialCategoriesEntitiesRelations.objects.get_or_create(entity, category, defaults={is_active: True, max_limit: 0.00})`, and a missing category rolls the whole create back to step 2 (branches WS2 / WC5 / WS7).

### 5.5 Deletion policy

No relation delete UI exists. The sanctioned removal is **deactivation** (`is_active=False` — bulk-unselect or the `remove` action); soft deletion of relations happens only through the entity's auto-delete path or the admin. Categories/relations have live-only unique names so reuse after soft-delete is intended.

---

## 6. Consumers contract (cross-app)

- `Operation.category` is a FK to `app_entity.FinancialCategory` (PROTECT). The generic operation create flow only offers categories **linked to the URL entity** (through the relation) when the proxy sets `has_category` (e.g. `ExpenseOperation`), and rejects an operation with no category when `has_category=True` (model `clean()` + `OperationDataValidator`).
- Tests across `app_operation` and `app_adjustment` seed categories with `FinancialCategory.objects.get_or_create` and link them with `FinancialCategoriesEntitiesRelations.objects.get_or_create(entity=…, category=…, defaults={max_limit: …})` — exactly the shape the bulk-assign and wizard views must produce.
- `seed` command creates the default category catalog.

---

## 7. View / UI contract

| Route (mounted at `/entities/`) | View | Method(s) | Purpose |
|----------------------------------|------|-----------|---------|
| `/entities/<int:parent_entity_id>/category/bulk-assign/` | `CategoryBulkAssignView` | GET/POST | toggle many category links for one entity at once |
| `/entities/category/edit/<int:pk>` | `CategoryRelationEditView` | GET/POST | per-relation remove / activate / save-max-limit |
| `/entities/category/detail/<int:pk>` | `CategoryRelationDetailView` | GET | read-only relation detail (usage % placeholder) |

- The bulk-assign form lists every category with the entity's currently-active relations pre-checked; submitting reflects the full desired set.
- The relation edit form posts an `action` (`remove` / `activate` / `save`) and, for `save`, a `max_limit`.
- All successful actions redirect to the owning entity's `entity_detail`.

---

## 8. Branch catalog (all possible branches)

- **bulk assign:** entity 404 (CA1) · activate/create selected (CA2) · deactivate unselected (CA3) · audit+counts+redirect (CA4) · GET context (CA5).
- **relation edit:** 404 (CR1) · max_limit validation (CR2) · remove deactivates (CR3) · activate (CR4) · save max_limit (CR5) · audit+message+redirect (CR6).
- **relation detail:** load/404 (CD1) · context with usage stub (CD2).
- **wizard link:** step-2 draft + Summary get_or_create (WS2/WC5/WS7 — see Project contract).
- **model invariants:** live-only unique category name · live-only unique (entity, category) · max_limit ≥ 0 · relations deactivated not deleted · PROTECT/auto-delete with owner.

## 9. Test coverage matrix

| Area | Test class / method | Branch(es) |
|------|---------------------|------------|
| Category name reuse | `FinancialCategoryUniqueReuseTests.test_soft_deleted_category_name_can_be_reused` · `test_live_duplicate_category_name_still_rejected` | §3 live-only unique name |
| Relation pair reuse | `EntityCategoryRelationUniqueReuseTests.test_soft_deleted_relation_can_be_recreated` · `test_live_duplicate_relation_still_rejected` | §3 live-only unique pair |
| Wizard step 2 | `ProjectSetupWizardStep2Test` (selection stored, no relations yet) | WS2 |
| Wizard linking/rollback | `ProjectSetupWizardIntegrationTest.test_complete_wizard_flow_creates_project_on_summary` · `test_category_failure_rolls_back_and_redirects_to_step_2` | WC5 / WS7 |
| Operation consumers | expense create/reversal/payment, correction, adjustment suites in `app_operation`/`app_adjustment` | §6 (category FK + required) |

**Known coverage gaps:** none of the three category **views** has a direct `app_entity` test (CA1–CA5, CR1–CR6, CD1–CD2 unpinned); there is no spending enforcement against `max_limit` and the relation-detail `usage_percentage` is a hard-coded stub (`0`) — both are behavior gaps to close (enforce cap or surface real usage; add view tests).
