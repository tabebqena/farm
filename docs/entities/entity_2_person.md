# Person — Entity Contract

**Epic:** Entity & Stakeholder Management — Parties
**Area app:** `app_entity`
**Actions:** `create`, `edit/update`, `activate/deactivate`, `detail`
**Contract status:** v1 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Person** entity (`Entity` with `entity_type=PERSON`) and its two views — create (`PersonCreateView`) and edit (`PersonEditView`) — driven by `PersonForm`.
> Every clause below names its implementing code (model → form → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Person reuses the shared Entity foundation — type/immutability/name-uniqueness/soft-delete/period-sync branches live in the [Entity lifecycle](entity_1_lifecycle.md) contract and are only cross-referenced here.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Model | `Entity` where `entity_type = EntityType.PERSON` | |
| Role choice-set | `EntityType.PERSON` (`"person"`) | |
| Form | `PersonForm` (ModelForm over `Entity`) | |
| Create view | `PersonCreateView` (URL `person/add/` → `person_create`) | |
| Edit view | `PersonEditView` (URL `person/edit/<int:pk>` → `person_edit`) | |
| Template | `app_entity/person_form.html` (shared by create + edit) | |
| Editable fields | `name`, `description`, `is_worker`, `is_vendor`, `is_client`, `is_shareholder`, `is_internal`, `active` | |
| Never exposed for edit | `entity_type` (fixed to PERSON), `user`, project-only fields | |
| Immutable fields | `entity_type`, `user` (from `Entity._immutable_fields`) | |
| Uniqueness (live-only) | `unique_entity_name_live` (+ friendly `PersonForm.clean_name` check) | |

---

## 2. Registered business logic (contract map)

### 2.1 Model / domain layer

| Concern | Implementing code |
|---------|-------------------|
| Person = `Entity` row with type PERSON | `Entity.create(entity_type=PERSON, …)` |
| Role predicates | `Entity.is_person` (+ the `is_vendor` / `is_client` / `is_worker` / `is_shareholder` flags) |
| Creation factory with proper defaults | `Entity.create` |
| Open financial-period auto-creation | `Entity.save()` |
| Type/immutability/name/soft-delete foundation | see [Entity lifecycle](entity_1_lifecycle.md) |

### 2.2 Form layer

| Concern | Implementing code |
|---------|-------------------|
| Person create/edit form | `PersonForm` |
| Live-only name uniqueness (friendly error, excludes self) | `PersonForm.clean_name` |
| `entity_type` pinned to PERSON on the form instance | `PersonForm.__init__` |
| Logging on validation | `LoggingFormMixin` |

### 2.3 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create (GET empty form / POST atomic create) | `PersonCreateView` |
| Edit (type guard + GET/POST) | `PersonEditView` |
| Redirect target on success | `entity_detail` |
| Lookup helper (custom 404 message) | `get_object_or_404` (farm shortcut) |

### 2.4 Cross-app consumers

| Concern | Consumer |
|---------|----------|
| Person as operation party / fund | e.g. Cash Injection destination, Cash Withdrawal source, Project Funding shareholder source, loan/worker-advance sides (see `docs/operations`) |
| Person as stakeholder target | worker / shareholder roles must be persons (see [Stakeholder](entity_4_stakeholder.md)); vendor/client persons act as external vendor/client parties in Purchase/Sale |

### 2.5 Tests

| Concern | Test file |
|---------|-----------|
| Person create view (GET/POST) | `app_entity.tests.test_entity_forms_person_create_view` |
| Person edit view (form) | `app_entity.tests.test_entity_forms_person_edit_view` |
| Person edit view (POST/validation/auth) | `app_entity.tests.test_views_post_person_edit_view` |

---

## 3. Domain model & invariants

- A Person is an `Entity` row whose `entity_type` is `PERSON`; it is never a project/system/world. The form pins `instance.entity_type = PERSON` on both create and edit.
- A person may carry any combination of the flat capability flags (`is_worker`, `is_vendor`, `is_client`, `is_shareholder`, `is_internal`) and `active`. These flags decide which stakeholder roles the person is eligible for and which operation roles the person can play.
- Name is required and must be unique among **live** entities (excluding the person being edited); `entity_type`/`user` are immutable.
- Creating an active person auto-creates its open `FinancialPeriod` (`Entity.save()`); deactivating closes it (see lifecycle contract §5.3).
- There is no delete UI for persons in the project — removal is an admin-only soft delete guarded by live dependents (lifecycle contract §5.5).

---

## 4. Derived financial contract

Person funds use the shared entity read-model: `balance_at` (payment types), `payables_at` / `receivables_at` (obligation types). See [Entity lifecycle](entity_1_lifecycle.md) §4. P&L is project-only and never computed for a person.

---

## 5. Actions

### 5.1 `create` — `PersonCreateView` (GET/POST `person/add/`)

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| PC1 | Name present | `name` non-empty | form error (re-render) | `"Name is required."` | `PersonForm.clean_name` | `PersonCreateViewTest.test_person_create_invalid_missing_name` |
| PC2 | Live name unique | no other **live** entity shares `name` | form error (re-render) | `"An entity with this name already exists."` | `PersonForm.clean_name` | `PersonCreateViewTest.test_person_create_invalid_duplicate_name` |
| PC3 | Auth | logged-in user | unauthenticated redirected to login | — | global auth | `PersonCreateViewTest.test_person_create_unauthenticated_user_redirected` |
| PC4 | Form errors preserve input | invalid form | re-render with the submitted form | — | `PersonCreateView.post` | `PersonCreateViewTest.test_person_create_form_preserved_on_error` |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| PS1 | Person entity created | `Entity.create(PERSON, **cleaned_data)` inside `transaction.atomic()` | `PersonCreateView.post` + `Entity.create` | `PersonCreateViewTest.test_person_create_post_creates_entity` · `test_person_create_uses_atomic_transaction` |
| PS2 | Type is PERSON | stored `entity_type == PERSON` | `Entity.create` | `PersonCreateViewTest.test_person_create_sets_correct_entity_type` |
| PS3 | Role flags applied | all four `is_*` flags reflect the form | `Entity.create` | `PersonCreateViewTest.test_person_create_with_all_roles` · `test_person_create_with_no_roles` |
| PS4 | Description stored | free-text description persists | `Entity.create` | `PersonCreateViewTest.test_person_create_with_description` |
| PS5 | Active status stored | `active` reflects the form checkbox | `Entity.create` (two-phase save) | `PersonCreateViewTest.test_person_create_sets_active_status` |
| PS6 | Open financial period | active person gets one open `FinancialPeriod` | `Entity.save()` | `PersonCreateViewTest.test_person_create_creates_financial_period` |
| PS7 | Success message + redirect | `person_created` audit, success message, redirect to `entity_detail` | `PersonCreateView.post` | `PersonCreateViewTest.test_person_create_displays_success_message` · `test_person_create_redirects_to_entity_detail` |

### 5.2 `edit` / `update` — `PersonEditView` (GET/POST `person/edit/<int:pk>`)

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| PE1 | Entity exists + live | pk resolves to a live entity | 404 (custom message) | `"Person not found or has been deleted."` | `get_object_or_404` | `PersonEditViewTest.test_nonexistent_entity_returns_404` |
| PE2 | Type guard: is a Person | `entity_type == PERSON` | message + redirect `entity_list` | `"This entity is not a Person."` | `PersonEditView._setup` | `PersonEditViewTest.test_edit_non_person_entity_shows_error` |
| PE3 | Name present | non-empty | form error (re-render) | `"Name is required."` | `PersonForm.clean_name` | `PersonEditViewTest.test_invalid_form_missing_name` |
| PE4 | Live name unique (excl. self) | no other live entity shares name | form error (re-render) | `"An entity with this name already exists."` | `PersonForm.clean_name` | `PersonEditViewTest.test_invalid_form_duplicate_name` · `test_person_can_use_own_name` |
| PE5 | Auth | logged-in user | redirect to login | — | global auth | `PersonEditViewTest.test_unauthenticated_user_redirected` |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| PS2E1 | Person updated | `PersonForm.save()` on the existing instance inside atomic | `PersonEditView.post` | `PersonEditViewTest.test_valid_form_updates_person` · `test_person_edit_post_updates_name` |
| PS2E2 | Roles updated | worker/vendor/client/shareholder flags set/cleared from the form | `PersonForm` | `test_person_edit_updates_roles` · `test_person_edit_removes_roles` |
| PS2E3 | Audit + message + redirect | `person_updated` audit, success message, redirect `entity_detail` | `PersonEditView.post` | `test_valid_form_displays_success_message` · `test_valid_form_redirects_to_detail` |

### 5.3 `detail`

Person detail is the shared `EntityDetailView` (financial summary + stakeholder/contact/category surfaces). See [Entity lifecycle](entity_1_lifecycle.md) §5.4.2.

### 5.4 Deletion policy

No person delete UI exists; admin-only soft delete with dependents guard (lifecycle §5.5).

---

## 6. Consumers contract (cross-app)

- Operations that name a Person as a required side enforce it via `is_person` — e.g. Cash Injection destination must be a person, Cash Withdrawal source must be a person, Internal Transfer parties are persons (see `docs/operations`).
- Stakeholder roles pin the person's capability flags: a person must be `is_worker` to be added as a worker, `is_shareholder` for shareholder, `is_vendor`/`is_client` for vendor/client (see [Stakeholder](entity_4_stakeholder.md) §5.1). Purchase and Sale consume the *active stakeholder* relationships on the vendor/client person.
- Person funds are real internal (or external) funds with the standard balance/obligation read-model.

---

## 7. View / UI contract

| Route (mounted at `/entities/`) | View | Method(s) | Purpose |
|----------------------------------|------|-----------|---------|
| `/entities/person/add/` | `PersonCreateView` | GET/POST | create a Person (empty form / atomic create) |
| `/entities/person/edit/<int:pk>` | `PersonEditView` | GET/POST | edit a Person (type guard first) |

- `person_form.html` is shared: create renders with `edit=False`, edit with `edit=True`.
- Successful create/edit redirects to `entity_detail`; type mismatches redirect to `entity_list` with an error message.
- Form fields are styled via `form-control`/`form-check-input` widgets; labels are the localized person/role labels.

---

## 8. Branch catalog (all possible branches)

- **create — validation:** name required (PC1) · live-name unique (PC2) · auth (PC3) · input preserved on error (PC4).
- **create — effects:** entity created atomically (PS1) · type PERSON (PS2) · role flags (PS3) · description (PS4) · active (PS5) · open period (PS6) · audit+message+redirect (PS7).
- **edit — validation:** 404 (PE1) · type guard (PE2) · name required (PE3) · live-name unique excl. self (PE4) · auth (PE5).
- **edit — effects:** update (PS2E1) · roles (PS2E2) · audit+message+redirect (PS2E3).

## 9. Test coverage matrix

| Area | Test class / method | Branch(es) |
|------|---------------------|------------|
| Create GET | `PersonCreateViewTest.test_person_create_get_renders_form` | — |
| Create — validation | `test_person_create_invalid_missing_name` · `test_person_create_invalid_duplicate_name` · `test_person_create_form_preserved_on_error` | PC1, PC2, PC4 |
| Create — effects | `test_person_create_post_creates_entity` · `test_person_create_sets_correct_entity_type` · `test_person_create_with_all_roles` · `test_person_create_with_no_roles` · `test_person_create_with_description` · `test_person_create_sets_active_status` · `test_person_create_creates_financial_period` · `test_person_create_uses_atomic_transaction` | PS1–PS6 |
| Create — UX | `test_person_create_displays_success_message` · `test_person_create_redirects_to_entity_detail` | PS7 |
| Create — auth | `test_person_create_unauthenticated_user_redirected` | PC3 |
| Edit GET | `PersonEditViewTest` (`test_entity_forms_person_edit_view.py`) `test_person_edit_get_renders_form` | — |
| Edit — form roles | `test_person_edit_post_updates_name` · `test_person_edit_updates_roles` · `test_person_edit_removes_roles` | PS2E1/PS2E2 |
| Edit — 404 | `test_person_edit_nonexistent_returns_404` | PE1 |
| Edit POST — success | `PersonEditViewTest` (`test_views_post_person_edit_view.py`) `test_valid_form_updates_person` · `test_valid_form_redirects_to_detail` · `test_valid_form_displays_success_message` | PS2E1–PS2E3 |
| Edit POST — validation | `test_invalid_form_missing_name` · `test_invalid_form_duplicate_name` · `test_person_can_use_own_name` | PE3, PE4 |
| Edit POST — type/auth/404 | `test_edit_non_person_entity_shows_error` · `test_unauthenticated_user_redirected` · `test_nonexistent_entity_returns_404` | PE2, PE5, PE1 |

**Known coverage gaps:** no dedicated test pins the person **deactivation → period close** path or the `entity_type` immutability guard at the person layer (both covered generically by the lifecycle contract gaps).
