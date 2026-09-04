# Project & Setup Wizard — Entity Contract

**Epic:** Entity & Stakeholder Management — Parties
**Area app:** `app_entity`
**Actions:** `create (wizard, 7-step, deferred)`, `edit/update`, `activate/deactivate`, `link categories`, `assign product templates`, `add worker/vendor/shareholder stakeholders`, `cancel`
**Contract status:** v1 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Project** entity (`Entity` with `entity_type=PROJECT`): the edit view (`ProjectEditView` / `ProjectForm`) and the create-only **7-step setup wizard** (`project_setup_wizard_view`) that defers creation to a session draft and commits atomically on the Summary step.
> Every clause below names its implementing code (model → form/wizard → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Project reuses the shared Entity foundation (type/immutability/name-uniqueness/soft-delete/period-sync) — see the [Entity lifecycle](entity_1_lifecycle.md) contract. Stakeholder links are specified in the [Stakeholder](entity_4_stakeholder.md) contract; category relations in the [Financial Categories](entity_6_financial_categories.md) contract.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Model | `Entity` where `entity_type = EntityType.PROJECT` | |
| Role choice-set | `EntityType.PROJECT` (`"project"`) | |
| Edit form | `ProjectForm` (ModelForm over `Entity`) | |
| Edit view | `ProjectEditView` (URL `project/edit/<int:pk>` → `project_edit`) | |
| Create view | `project_setup_wizard_view` (URLs `project/setup/` → `project_create`, `project/setup/<int:step>/` → `project_setup`, `project/setup/cancel/` → `project_setup_cancel`) | |
| Wizard steps | 1 Project Info · 2 Categories · 3 Product Templates · 4 Workers · 5 Vendors · 6 Shareholders · 7 Summary | |
| Wizard storage | session draft under key `project_setup_wizard` | |
| Templates | `app_entity/project_form.html`, `app_entity/project_setup_wizard.html` (+ `setup/step_*.html` partials) | |
| Editable fields (ProjectForm) | `name`, `description`, `is_client`, `is_vendor`, `is_internal`, `active` | |
| Never set on a project | `is_worker`, `is_shareholder` (no form field; wizard never offers client) | |
| Immutable fields | `entity_type`, `user` (from `Entity._immutable_fields`) | |
| Uniqueness (live-only) | `unique_entity_name_live` (+ `ProjectForm.clean_name`) | |

---

## 2. Registered business logic (contract map)

### 2.1 Model / domain layer

| Concern | Implementing code |
|---------|-------------------|
| Project = `Entity` row with type PROJECT | `Entity.create(entity_type=PROJECT, …)` |
| Project-only derived financials (`profit_loss`, inventory, end-assets) | lifecycle contract §4 + `app_inventory` / `FinancialPeriod` |
| Open financial-period auto-creation | `Entity.save()` |
| Product templates M2M | `entity.product_templates` (managed by wizard, step 3) |

### 2.2 Form / wizard layer

| Concern | Implementing code |
|---------|-------------------|
| Project edit form + live-name uniqueness | `ProjectForm` / `ProjectForm.clean_name` |
| Wizard entry + step routing + guards | `project_setup_wizard_view` |
| Wizard cancel | `project_setup_cancel_view` |
| Session draft helpers | `_draft_get` / `_draft_save` / `_draft_clear` |
| Step POST handlers | `_handle_step_1_post` … `_handle_step_7_post`, `_handle_stakeholder_post` |
| Atomic create + per-stage error mapping | `_apply_create_project` + `_WizardStageError` |
| Stage helpers | `_link_categories`, `_assign_templates`, `_create_stakeholders`, `_role_filter` |
| Step context builders | `_get_step_context`, `_step2_context`, `_step3_context`, `_stakeholder_context`, `_summary_context` |

### 2.3 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Edit view (type guard + GET/POST) | `ProjectEditView` |
| Redirect targets | `entity_detail` (success), `entity_list` (invalid step / cancel), `project_create` (expired draft), `project_setup` step N (per-stage failure) |

### 2.4 Cross-app consumers

| Concern | Consumer |
|---------|----------|
| Project as operation source/destination/fund | nearly every operation spec (`docs/operations`) — the project is the farm unit of account |
| Project-only reports (P&L, balance sheet, inventory value) | `app_report`, `FinancialPeriod.end_assets` |
| Product templates scoped to the project | `app_inventory` stock/ledger machinery |
| Stakeholder links created by the wizard | Purchase (vendor), Sale (client), Worker Advance (worker), Project Funding/Refund (shareholder) |

### 2.5 Tests

| Concern | Test file |
|---------|-----------|
| Project edit view (form) | `app_entity.tests.test_entity_forms_project_edit_view` |
| Project edit view (POST/validation/auth) | `app_entity.tests.test_views_post_project_edit_view` |
| Wizard step 1 | `app_entity.tests.test_project_setup_wizard_project_setup_wizard_step1` |
| Wizard step 2 | `…_step2` |
| Wizard step 3 | `…_step3` |
| Wizard step 4 | `…_step4` |
| Wizard step 5 | `…_step5` |
| Wizard step 6 | `…_step6` |
| Wizard full flow + rollback | `…_integration` |

---

## 3. Domain model & invariants

- A Project is an `Entity` row with `entity_type = PROJECT`. It may be `is_internal`, `is_client` and/or `is_vendor`; it is **never** a worker or shareholder (the model's stakeholder `clean()` rejects a project target for worker/shareholder roles — see [Stakeholder](entity_4_stakeholder.md)).
- Name is required and unique among live entities (excluding self on edit). `entity_type`/`user` immutable.
- Project funds are the only funds with a `profit_loss` (P&L), and project entities carry the inventory/product-templates the farm runs on.
- The setup wizard is **create-only and deferred**: steps 1–6 write only to the session draft, and the Summary **Create** commits the project plus its categories, product templates and worker/vendor/shareholder stakeholder links inside **one** `transaction.atomic()` block. Any per-stage failure rolls the whole creation back and bounces the user to the failing step with the draft intact.
- Default project info for a fresh wizard: `is_client=True`, `is_vendor=True`, `active=True`, `is_internal=False` — so a new farm project can receive invoices and charge expenses out of the box (unchecking stores `False`).
- There is no delete UI for projects; removal is an admin-only soft delete guarded by live dependents (lifecycle §5.5).

---

## 4. Derived financial contract

Projects use the shared read-model plus project-only derivations: `profit_loss` (raises for non-projects), movement-based inventory value, `FinancialPeriod` end-assets/end-liabilities. See [Entity lifecycle](entity_1_lifecycle.md) §4 and the period/report feature docs; deep branches are pinned by the operation/report suites.

---

## 5. Actions

### 5.1 Wizard `create` (7-step, deferred; URLs `project/setup/…`)

#### 5.1.1 Routing & guard branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| WC1 | Step is valid | `step in STEPS` (1..7) | message + redirect `entity_list` | `"Invalid wizard step."` | `project_setup_wizard_view` | no direct pinning test in `app_entity` suite (gap) |
| WC2 | Draft started before later steps | steps 2–7 require `draft.info.name` | message + redirect `project_create` | `"Session expired. Please start from the beginning."` | `project_setup_wizard_view` | `ProjectSetupWizardStep1Test.test_wizard_later_step_requires_started_draft` (+ each step's `…_requires_started_draft`) |
| WC3 | Step 1 name present | non-empty name | message + redirect `project_create` (no draft) | `"Project name is required."` | `_handle_step_1_post` | `ProjectSetupWizardStep1Test.test_wizard_step_1_requires_name` |

#### 5.1.2 Per-step success effects (draft only — nothing persists before Summary)

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| WS1 | Step 1 stores project info | `draft["info"]` = name/description/is_internal/is_vendor/is_client/active; **no** `Entity` row | `_handle_step_1_post` | `ProjectSetupWizardStep1Test.test_wizard_step_1_stores_draft_without_creating_project` · `test_wizard_step_1_defaults_client_and_vendor` |
| WS2 | Step 2 stores categories | `draft["categories"]` = sorted selected category pks; no relations yet | `_handle_step_2_post` | `…_step2.test_wizard_step_2_stores_selection_without_linking` · `test_wizard_step_2_get_shows_categories` |
| WS3 | Step 3 stores product templates | `draft["templates"]` = selected template pks; **staff only** (non-staff POST denied, nothing stored) | `_handle_step_3_post` | `…_step3.test_wizard_step_3_staff_stores_templates` · `test_wizard_step_3_non_staff_denied` · `test_wizard_step_3_get_shows_templates` |
| WS4 | Steps 4–6 store stakeholder ids | `draft["workers"]/["vendors"]/["shareholders"]` per role; no `Stakeholder` rows yet | `_handle_stakeholder_post` | `…_step4/5/6 .test_wizard_step_*_stores_*_without_linking` · `…_get_reflects_selection` |
| WS5 | Cancel clears the draft | `wizard_cancelled` audit, info message, redirect `entity_list` | `project_setup_cancel_view` | `ProjectSetupWizardStep1Test.test_wizard_cancel_clears_draft` |

#### 5.1.3 Summary create (step 7 POST) — validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| WC4 | Project name still present in draft | `draft.info.name` non-empty | `_WizardStageError` (step 1) → redirect step 1 | `"Project name is required."` | `_apply_create_project` | covered by WS1 validation flow |
| WC5 | Selected categories still exist | each `draft["categories"]` pk resolves | `_WizardStageError` (step 2) → redirect step 2, whole create rolled back | `"A selected category no longer exists. …"` | `_link_categories` | `ProjectSetupWizardIntegrationTest.test_category_failure_rolls_back_and_redirects_to_step_2` |
| WC6 | Selected templates still exist | each `draft["templates"]` pk resolves (staff only) | `_WizardStageError` (step 3) → redirect step 3 | `"A selected product template no longer exists. …"` | `_assign_templates` | covered by step 3 staff tests + integration (no direct missing-template test in `app_entity` suite — gap) |
| WC7 | Selected stakeholders still exist + eligible | each target resolves with the role's eligibility filter (`is_worker`/`is_vendor`/`is_shareholder` + active) | `_WizardStageError` (steps 4/5/6) → redirect to that step | `"A selected worker no longer exists or is no longer eligible for that role."` etc. | `_create_stakeholders` | `ProjectSetupWizardIntegrationTest.test_worker_failure_redirects_to_step_4` |

#### 5.1.4 Summary create — success effects (single atomic block)

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| WS6 | Project entity created | `Entity.create(PROJECT, name, description, is_internal, is_vendor, is_client, active)`; `wizard_project_created` audit | `_apply_create_project` | `ProjectSetupWizardIntegrationTest.test_complete_wizard_flow_creates_project_on_summary` |
| WS7 | Categories linked | active `FinancialCategoriesEntitiesRelations` per selected category with `max_limit=0.00` | `_link_categories` | integration (category assertions) |
| WS8 | Product templates assigned | `entity.product_templates.set(templates)` (staff) | `_assign_templates` | integration (template assertions) |
| WS9 | Worker/vendor/shareholder links created | `Stakeholder.get_or_create(parent=entity, target, role)` per selected id | `_create_stakeholders` | integration (stakeholder assertions) |
| WS10 | Draft cleared + success | `wizard_completed` audit, success message, redirect `entity_detail` | `_handle_step_7_post` | integration test (redirect/entity) |

### 5.2 `edit` / `update` — `ProjectEditView` (GET/POST `project/edit/<int:pk>`)

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| PJ1 | Entity exists + live | pk resolves to a live entity | 404 (custom message) | `"Project not found or has been deleted."` | `get_object_or_404` | `ProjectEditViewTest.test_nonexistent_entity_returns_404` |
| PJ2 | Type guard: is a Project | `entity_type == PROJECT` | message + redirect `entity_list` | `"This entity is not a Project."` | `ProjectEditView._setup` | `ProjectEditViewTest.test_edit_non_project_entity_shows_error` |
| PJ3 | Name present | non-empty | form error (re-render) | `"Project name is required."` | `ProjectForm.clean_name` | `ProjectEditViewTest.test_invalid_form_missing_name` |
| PJ4 | Live name unique (excl. self) | no other live entity shares name | form error (re-render) | `"A project with this name already exists."` | `ProjectForm.clean_name` | `ProjectEditViewTest.test_invalid_form_duplicate_name` · `test_project_can_use_own_name` |
| PJ5 | Auth | logged-in user | redirect to login | — | global auth | `ProjectEditViewTest.test_unauthenticated_user_redirected` |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| PJ6 | Project updated | `ProjectForm.save()` on the existing instance inside atomic | `ProjectEditView.post` | `ProjectEditViewTest.test_valid_form_updates_project` · `test_project_edit_post_updates_name` · `test_project_edit_updates_description` |
| PJ7 | Audit + message + redirect | `project_updated` audit, success message, redirect `entity_detail` | `ProjectEditView.post` | `test_valid_form_displays_success_message` · `test_valid_form_redirects_to_detail` |

### 5.3 `detail`

Project detail is the shared `EntityDetailView` — it is the redirect target of both the wizard and the edit view and carries the financial-summary card (see lifecycle §5.4.2).

### 5.4 Deletion policy

No project delete UI exists; admin-only soft delete with dependents guard (lifecycle §5.5).

---

## 6. Consumers contract (cross-app)

- Nearly every operation names a **project** as source or destination (`_source_role`/`_dest_role`) and drives the pickers from the project's stakeholder links — Purchase's vendors, Sale's clients, Worker Advance's workers, Project Funding/Refund's shareholders. Each op spec pins the required active-stakeholder shape.
- Project funds are the only funds with `profit_loss`, movement-based inventory value, and closed-period end-assets — surfaced by `app_report` and `FinancialPeriod`.
- The wizard (step 3) and the wizard-summary template assignment write the project's `product_templates` M2M, which `app_inventory` reads to scope product creation to the project.

---

## 7. View / UI contract

| Route (mounted at `/entities/`) | View | Method(s) | Purpose |
|----------------------------------|------|-----------|---------|
| `/entities/project/setup/` | `project_setup_wizard_view` | GET/POST | wizard step 1 (Project Info) |
| `/entities/project/setup/<int:step>/` | `project_setup_wizard_view` | GET/POST | wizard steps 2–7 |
| `/entities/project/setup/cancel/` | `project_setup_cancel_view` | GET | abandon + clear draft |
| `/entities/project/edit/<int:pk>` | `ProjectEditView` | GET/POST | edit an existing project |

- The wizard template (`project_setup_wizard.html`) renders each step from `step`, `total_steps`, `step_labels` and `step_nums`; per-step partials under `app_entity/setup/` show project info, categories grouped by aspect, product templates, eligible stakeholders, and the read-only Summary.
- Step 3 lists product templates **only for staff**; other users see an empty list and a denied message on POST.
- On Summary failure the user is redirected to the failing step (1–6) with the session draft preserved so they can correct and re-submit.
- `project_form.html` is shared by create/edit contexts (`edit=False`/`edit=True`) — but in practice projects are created via the wizard, so the edit view always renders with an existing instance.

---

## 8. Branch catalog (all possible branches)

- **wizard — routing/guards:** invalid step (WC1) · draft required for later steps (WC2) · step-1 name required (WC3).
- **wizard — draft effects:** step 1 info stored, no entity (WS1) · step 2 categories stored, no relations (WS2) · step 3 templates stored, staff only (WS3) · steps 4–6 stakeholder ids stored, no rows (WS4) · cancel clears draft (WS5).
- **wizard — summary create:** name present (WC4) · categories exist (WC5) · templates exist (WC6) · stakeholders exist + eligible (WC7) · project + relations + links created atomically (WS6–WS9) · draft cleared + redirect (WS10).
- **edit — validation:** 404 (PJ1) · type guard (PJ2) · name required (PJ3) · live-name unique excl. self (PJ4) · auth (PJ5).
- **edit — effects:** update (PJ6) · audit+message+redirect (PJ7).

## 9. Test coverage matrix

| Area | Test class / method | Branch(es) |
|------|---------------------|------------|
| Wizard step 1 | `ProjectSetupWizardStep1Test.test_wizard_step_1_get_renders_form` · `test_wizard_step_1_defaults_client_and_vendor` · `test_wizard_step_1_stores_draft_without_creating_project` · `test_wizard_step_1_requires_name` · `test_wizard_later_step_requires_started_draft` · `test_wizard_cancel_clears_draft` | WC2, WC3, WS1, WS5 |
| Wizard step 2 | `ProjectSetupWizardStep2Test.test_wizard_step_2_get_shows_categories` · `test_wizard_step_2_stores_selection_without_linking` · `test_wizard_step_2_requires_started_draft` | WS2, WC2 |
| Wizard step 3 | `ProjectSetupWizardStep3Test.test_wizard_step_3_staff_stores_templates` · `test_wizard_step_3_get_shows_templates` · `test_wizard_step_3_non_staff_denied` · `test_wizard_step_3_requires_started_draft` | WS3, WC2 |
| Wizard step 4 | `ProjectSetupWizardStep4Test.test_wizard_step_4_stores_workers_without_linking` · `test_wizard_step_4_get_reflects_selection` · `test_wizard_step_4_requires_started_draft` | WS4, WC2 |
| Wizard step 5 | `ProjectSetupWizardStep5Test.test_wizard_step_5_stores_vendors_without_linking` · `test_wizard_step_5_get_reflects_selection` · `test_wizard_step_5_requires_started_draft` | WS4, WC2 |
| Wizard step 6 | `ProjectSetupWizardStep6Test.test_wizard_step_6_stores_shareholders_without_linking` · `test_wizard_step_6_get_reflects_selection` · `test_wizard_step_6_requires_started_draft` | WS4, WC2 |
| Wizard integration | `ProjectSetupWizardIntegrationTest.test_complete_wizard_flow_creates_project_on_summary` · `test_category_failure_rolls_back_and_redirects_to_step_2` · `test_worker_failure_redirects_to_step_4` | WC5, WC7, WS6–WS10 |
| Edit GET | `ProjectEditViewTest` (`test_entity_forms_project_edit_view.py`) `test_project_edit_get_renders_form` | — |
| Edit — form | `test_project_edit_post_updates_name` · `test_project_edit_updates_description` · `test_project_edit_nonexistent_returns_404` | PJ6, PJ1 |
| Edit POST — success | `ProjectEditViewTest` (`test_views_post_project_edit_view.py`) `test_valid_form_updates_project` · `test_valid_form_redirects_to_detail` · `test_valid_form_displays_success_message` | PJ6, PJ7 |
| Edit POST — validation | `test_invalid_form_missing_name` · `test_invalid_form_duplicate_name` · `test_project_can_use_own_name` | PJ3, PJ4 |
| Edit POST — type/auth/404 | `test_edit_non_project_entity_shows_error` · `test_unauthenticated_user_redirected` · `test_nonexistent_entity_returns_404` | PJ2, PJ5, PJ1 |

**Known coverage gaps:** no direct pinning test for invalid wizard step (WC1), staff-only template-create rollback on a missing template (WC6), or the project deactivation→period-close / type-immutability guards (lifecycle gaps).
