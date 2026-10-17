# Entity Lifecycle & Types — Entity Contract

**Epic:** Entity & Stakeholder Management — Foundation
**Area app:** `app_entity`
**Actions:** `create`, `edit/update`, `activate`, `deactivate`, `list`, `detail`, `delete (admin-only)`
**Contract status:** v1 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the shared **Entity** foundation of the `app_entity` app — the single `Entity` table (person / project / system / world), its lifecycle, its derived financial read-model, and the two shared views (list, detail) that serve every entity kind.
> Every clause below names its implementing code (model → base machinery → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> This is the foundation the other entity areas build on — see [`_ENTITY_SPEC_TEMPLATE.md`](_ENTITY_SPEC_TEMPLATE.md) and the [Person](entity_2_person.md) / [Project](entity_3_project.md) contracts for the concrete create/edit flows that use `Entity.create`.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Model | `Entity` (single table for all parties + virtual counters) | |
| Type choice-set | `EntityType` — `PERSON`, `PROJECT`, `SYSTEM`, `WORLD` | |
| Managers | `Entity.objects` (live only) / `Entity.all_objects` (incl. soft-deleted) | |
| Immutable fields | `entity_type`, `user` (via `_immutable_fields`) | |
| Uniqueness (live-only) | `unique_entity_name_live` — one live `name` per entity | |
| Virtual singletons | exactly one `SYSTEM`, exactly one `WORLD` (enforced in `clean()` on create) | |
| Admin | `EntityClass` (registered `Entity`) — admin-only delete | |
| Soft-delete auto relations | `contacts`, `stakeholders`, `memberships`, `financial_categories_entities_relations`, `financial_periods` | |

**Flat metadata fields:** `name` (required at form layer), `description`, project-only `feasibility_study` / `start_date` / `end_date`, optional `user` (OneToOne, PROTECT), `is_internal`, role flags `is_vendor` / `is_client` / `is_worker` / `is_shareholder`, `active`.

---

## 2. Registered business logic (contract map)

### 2.1 Model / domain layer

| Concern | Implementing code |
|---------|-------------------|
| `Entity` model + `EntityType` choices + `clean()` type rules + `create()` factory | |
| Role predicates `is_system` / `is_world` / `is_virtual` / `is_project` / `is_person` | |
| `get_display_name()` / `__str__()` / `get_absolute_url()` (→ `entity_detail`) | |
| Immutability of `entity_type` + `user` | `_immutable_fields` on `Entity` |
| Open financial-period sync on activation / deactivation | `Entity.save()` |
| Soft-delete audit override | `Entity.delete()` |
| Derived financial read-model (`balance_at`, `payables_at`, `receivables_at`, `profit_loss`, `balance`/`payables`/`receivables`, `can_pay`) | |

### 2.2 Shared base layer (`app_base`)

| Concern | Implementing code |
|---------|-------------------|
| Soft-delete + delete guard (`get_delete_blockers`, `_auto_soft_delete_dependents`, `_perform_soft_delete`) | `BaseModel` |
| Live-only manager, no bulk writes | `ActiveManager` / `SafeQuerySet` / `DefaultManager` |
| Save-time immutability guard | `ImmutableMixin` |
| Audit fields | `BaseModel` |
| Audit + error logging | `audit_logger` / `logger` |

### 2.3 Cross-app consumers

| Concern | Consumer |
|---------|----------|
| Entity types + role flags drive every operation's `clean_source` / `clean_destination` / `clean` | all operation specs (`docs/operations`) |
| `balance_at` / `can_pay` = the fund ledger used by payment-type txs | `Transaction` / every payment branch in operation specs |
| `payables_at` / `receivables_at` = obligation read-model | Purchase/Sale/Expense/Worker Advance/Loan specs |
| `profit_loss` = project P&L | `app_report` income statement, `FinancialPeriod.amount` |
| `Entity.save()` keeps each real entity's open `FinancialPeriod` in sync | `FinancialPeriod` (period specs) |
| Virtual `SYSTEM` / `WORLD` singletons as operation counter-parties | e.g. Cash Injection (world), Correction Debit (system), Capital Loss (system) |
| `Entity.objects.create` blocked without role/type via `Entity.create` | every app's test seeders + `seed` command |

### 2.4 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Entity list (search + type/deletion/activation filters) | `EntityListView` |
| Entity detail (+ payables / receivables / stock value) | `EntityDetailView` |
| URLs | `` (list), `<int:pk>/` (detail) — mounted under `entities/` |
| Templates | `app_entity/entity_list.html`, `app_entity/entity_detail.html` |
| Lookup helper (custom 404 message) | `get_object_or_404` in `farm/shortcuts` |

### 2.5 Tests

| Concern | Test file |
|---------|-----------|
| List view GET + list filters | `app_entity.tests.test_views_get_entity_list_view`, `test_entity_list_filters_*` (5 files) |
| Detail view GET + financial summary context | `app_entity.tests.test_views_get_entity_detail_view` |
| Soft-delete guard + auto-delete + circular links | `app_entity.tests.test_soft_delete_guard` |
| Live-only name reuse | `app_entity.tests.test_soft_delete_unique_reuse` |
| Period auto-create / virtual exemption | `app_operation.tests.period.test_financial_period_entity_period_auto_create` (+ operation suites) |

---

## 3. Domain model & invariants

- **One table, four kinds.** `entity_type` is a `TextChoices` on `Entity`: `person`, `project`, `system`, `world`. `system` + `world` are **virtual** (`is_virtual`), are singletons, and never get financial periods.
- **Immutability.** `entity_type` and `user` cannot change after first save (`_immutable_fields`). The UI never edits them; changing them raises `"You can't edit this field …"` from `ImmutableMixin.save()`.
- **Unique live name.** DB constraint `unique_entity_name_live` scopes name uniqueness to rows with `deleted_at IS NULL`, so a soft-deleted entity's name can be reused (the old `unique=True` is gone). Person/Project forms mirror this with a friendlier live-only duplicate check (see Person/Project contracts).
- **Virtual singleton clean rules.** On create, `SYSTEM` forces `is_internal=True`; `WORLD` forces `is_internal=False`; a virtual entity clears every role flag (`is_vendor`, `is_worker`, `is_client`, `is_shareholder`). Only one `SYSTEM` and one `WORLD` may ever exist.
- **Role flags are optional identity, not type.** `is_vendor` / `is_client` / `is_worker` / `is_shareholder` on a person/project are the flat "capability" flags that stakeholder assignment (and operations like Purchase/Sale/Worker Advance) read; they never override `entity_type`.
- **Soft-delete / PROTECT semantics.** `Entity.delete()` is a soft delete (stamps `deleted_at`). The `BaseModel` guard blocks deletion while **live financial-history dependents** exist (products, operations, transactions and other records whose FK is PROTECT/CASCADE and which are *not* auto-declared). The *owned light rows* — `contacts`, `stakeholders`, `memberships` (target side), `financial_categories_entities_relations`, `financial_periods` — are declared in `_delete_auto_relations` and are **auto soft-deleted** with the entity (which also breaks circular person↔project links). Deletion is an **admin-only** action; no project UI view/form/button calls `Entity.delete()`.
- **`Entity.create()` factory is the sanctioned way to create entities** (used by every view, seeder and the wizard): it wraps creation in `transaction.atomic()`, applies canonical names for the singletons, saves once with `active=False`, then re-saves with the requested `active` value, so the open-period logic in `Entity.save()` runs with the final state.
- **Open period sync lives in `Entity.save()`.** A real (non-virtual) entity gets an open `FinancialPeriod` on creation/activation when none exists; deactivating a real entity closes its open period (end today, min start+1 day).

---

## 4. Derived financial contract

All balances are derived read-models over `Transaction`; no balance column is stored on `Entity`. (This contract is the same read-model the operation specs rely on; deep per-type branches are pinned in those suites.)

| Read-model | Scope | Formula (invariant) | Virtual exemption |
|-----------|-------|---------------------|-------------------|
| `balance_at(dt)` / `balance` | every entity fund | incoming **payment-type** txs ≤ dt − outgoing payment-type txs ≤ dt (reversed **and** reversal rows included so cross-period reversals land correctly) | virtual entities may go negative — never enforced |
| `payables_at(dt)` / `payables` | person + project | net of obligation types (issuance / adjustment increase as source or target) using `_tx_sum_excluding_reversed` (reversed before dt excluded; originals reversed after dt still counted; reversal rows excluded) | virtual have no obligations |
| `receivables_at(dt)` / `receivables` | person + project | mirror of payables on the other side | virtual have no obligations |
| `profit_loss(period=None)` | **project only** | income types (target side) − cost types (source side), reversal rows negated, sliced `[start_date, end_date)` when a period is given; **raises** for non-project funds | N/A — project only |
| `can_pay(amount)` | payer funds | `False` if inactive; `True` (no check) if virtual or not `is_internal`; else `balance >= amount` | virtual / external always `True` |

- Income/cost type lists are centralized in module-level helpers (`_profit_loss_income_types`, `_profit_loss_cost_types`, `_fund_transaction_sum`) and reference issuance + adjustment transaction types only — Capital Gain/Loss and Consumption are not accounting txs and never hit P&L (they flow through inventory value).
- `get_absolute_url()` returns `entity_detail`; list/detail templates render the derived values (see §7).

---

## 5. Actions

### 5.1 `create` (domain factory `Entity.create`)

Entry points: `Entity.create(entity_type, name=…, is_* flags, active=…)` — used by `PersonCreateView`, the project setup wizard, seeders across every app, and the `seed` command.

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | Entity type provided | `entity_type` set | `ValidationError` | `"Entity type is required. --"` | `Entity.clean()` | no direct pinning test in `app_entity` suite (gap) |
| VC2 | `SYSTEM` is a singleton | no live `SYSTEM` row exists on create | `ValidationError` | `"System entity already exists."` | `Entity.clean()` | no direct pinning test in `app_entity` suite (gap; exercised indirectly by one-per-DB test helpers and `seed`) |
| VC3 | `WORLD` is a singleton | no live `WORLD` row exists on create | `ValidationError` | `"World entity already exists."` | `Entity.clean()` | no direct pinning test in `app_entity` suite (gap; exercised indirectly) |
| VC4 | Role flags cleared on virtual | `SYSTEM`/`WORLD` never carry vendor/worker/client/shareholder flags | flags forced off in `clean()` | — (forced, not an error) | `Entity.clean()` | no direct pinning test in `app_entity` suite (gap) |
| VC5 | Live name unique | no other **live** row shares `name` | DB `IntegrityError` → form shows friendly error before save | constraint `unique_entity_name_live` | form `clean_name` + DB | `PersonCreateViewTest.test_person_create_invalid_duplicate_name` · `EntityNameReuseAfterSoftDeleteTests` |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | Row persisted (atomic) | entity saved inside `transaction.atomic()` | `Entity.create` | `PersonCreateViewTest.test_person_create_uses_atomic_transaction` |
| SC2 | Correct type stored | `entity_type` as requested (person/project/system/world) | `Entity.create` | `PersonCreateViewTest.test_person_create_sets_correct_entity_type` |
| SC3 | Virtual canonical names | `SYSTEM` → `"System"`, `WORLD` → `"World"` | `Entity.create` | no direct pinning test (gap; implied by seed/helpers) |
| SC4 | Role/active flags applied | `is_*` flags and final `active` reflect the requested values | `Entity.create` (two-phase save) | `PersonCreateViewTest.test_person_create_with_all_roles` · `test_person_create_with_no_roles` · `test_person_create_sets_active_status` |
| SC5 | Open period auto-created | real active person/project gets one open `FinancialPeriod`; its `start_date` is the entity's `start_date` when set, otherwise the creation date | `Entity.save()` | `PersonCreateViewTest.test_person_create_creates_financial_period` · `FinancialPeriodEntityPeriodAutoCreateTest` |
| SC6 | Virtual entities get no period | world/system skip the period sync entirely | `Entity.save()` | `FinancialPeriodEntityPeriodAutoCreateTest.test_world_entity_does_not_get_period` · `test_system_entity_does_not_get_period` |

### 5.2 `edit` / `update`

Person/project edits go through `PersonForm` / `ProjectForm` (their own contracts). The shared entity-level rules that apply to any update:

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| EU1 | `entity_type` unchanged | same value after save | `ValidationError` | `"You can't edit this field entity_type"` | `ImmutableMixin.save()` | no direct pinning test in `app_entity` suite (gap; generic immutability covered by `app_base.tests.test_mixins`) |
| EU2 | `user` unchanged | same value after save | `ValidationError` | `"You can't edit this field user"` | `ImmutableMixin.save()` | no direct pinning test in `app_entity` suite (gap) |
| EU3 | Live name unique on rename | no other live row shares the new name (excluding self) | form error | `"An entity with this name already exists."` / `"A project with this name already exists."` | form `clean_name` | `PersonEditViewTest.test_invalid_form_duplicate_name` · `ProjectEditViewTest.test_invalid_form_duplicate_name` · `…test_person_can_use_own_name` |

### 5.3 `activate` / `deactivate`

Activation is a **data state** (`active`) edited through the person/project forms and seed, and it has a hard side effect in `Entity.save()`:

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| AC1 | Deactivate a real entity with an open period | `active=False` on save | open `FinancialPeriod` closed (end = today, min start+1 day) | — (side effect) | `Entity.save()` | no direct pinning test in `app_entity` suite (gap) |
| AC2 | Activate a real entity with no open period | `active=True` and no open period | new open `FinancialPeriod` created (start = today) | — (side effect) | `Entity.save()` | period suite (`FinancialPeriodEntityPeriodAutoCreateTest`) |
| AC3 | World/system unaffected by activation state | entity virtual | period sync skipped | — | `Entity.save()` | `…test_world_entity_does_not_get_period` / `…test_system_entity_does_not_get_period` |
| AC4 | Inactive entity cannot pay | `active` required by `can_pay` | `can_pay(...) == False` | — | `Entity.can_pay` | operation balance suites (inactive-fund tests in op specs) |

### 5.4 `list` / `detail`

#### 5.4.1 `EntityListView` (GET, URL `` → `entity_list`)

Validation/scoping branches:

| # | Branch | Behavior | Enforced by | Pinned by test |
|---|--------|----------|-------------|----------------|
| LV1 | Base queryset | starts from `Entity.all_objects` so the deleted filter can see tombstones | `EntityListView.get` | `EntityListViewTest` |
| LV2 | Type filter (`type`) | `person` → PERSON; `project` → PROJECT; `system_world` → SYSTEM+WORLD; `all` (default) → **excludes** SYSTEM+WORLD | `EntityListView.get` | `EntityListFilterByTypeTest` (4 tests) |
| LV3 | Deletion filter (`deletion`) | `deleted` → `deleted_at IS NOT NULL`; `undeleted` (default) → live only | `EntityListView.get` | context/filter tests |
| LV4 | Activation filter (`activation`) | `active` (default) → `active=True`; `inactive` → `active=False` | `EntityListView.get` | `EntityListFilterByActivationTest` |
| LV5 | Search (`q`) | `name__icontains` case-insensitive substring | `EntityListView.get` | `EntityListSearchTest` |
| LV6 | Combined filters | type + deletion + activation + search compose (AND) | `EntityListView.get` | `EntityListCombinedFiltersTest` |
| LV7 | Context | exposes `entities`, `type_filter`, `deletion_filter`, `activation_filter`, `search_query` | view context | `EntityListContextDataTest` |
| LV8 | Auth | unauthenticated users are redirected | global auth (login-required middleware) | `EntityListViewTest.test_unauthenticated_user_redirected_from_entity_list` |

#### 5.4.2 `EntityDetailView` (GET, URL `<int:pk>/` → `entity_detail`)

| # | Branch | Behavior | Enforced by | Pinned by test |
|---|--------|----------|-------------|----------------|
| DV1 | Load | live entity by pk (`Entity.objects`); soft-deleted/missing → 404 with message | `get_object_or_404` (farm shortcut) | `EntityDetailViewTest.test_nonexistent_entity_detail_returns_404` |
| DV2 | Edit target | navigation Edit link → `project_edit` for PROJECT else `person_edit` | `EntityDetailView.get` | detail navigation tests |
| DV3 | Financial summary | context carries `payables`, `receivables`, `stock_value` (`inventory_value(entity, today)`), `currency` (`settings.CURRENCY_SYMBOL`) | view + `Entity.payables`/`receivables` + `stock.inventory_value` | `EntityDetailViewTest.test_entity_detail_context_has_financial_summary` · `test_entity_detail_reflects_payables` · `test_entity_detail_reflects_stock_value` · `test_entity_detail_financial_summary_links_and_balance` |
| DV4 | Stakeholders | detail template renders stakeholder/membership links | template + reverse relations | `EntityDetailViewTest.test_entity_detail_with_stakeholders` |
| DV5 | Auth | unauthenticated users are redirected | global auth | `EntityDetailViewTest.test_unauthenticated_user_redirected_from_entity_detail` |

### 5.5 `delete` (admin-only, soft)

`Entity.delete()` is reachable only through Django admin (staff superuser). The project UI must never expose it.

| # | Branch | Behavior | Enforced by | Pinned by test |
|---|--------|----------|-------------|----------------|
| DL1 | Live financial dependents exist | deletion **blocked** — `ValidationError` (code `delete_blocked`) names the dependents (e.g. products/operations) | `BaseModel.get_delete_blockers` | `EntityGuardTests.test_delete_blocked_while_live_child_exists` · `test_get_delete_blockers_lists_dependents` |
| DL2 | Blocked delete leaves auto children untouched | guard fails before `_auto_soft_delete_dependents` runs | `BaseModel.delete` ordering | `EntityGuardTests.test_auto_children_untouched_when_guard_blocks` |
| DL3 | Leaf-up delete succeeds | once the blocking dependents are removed, entity deletes | `BaseModel.delete` | `EntityGuardTests.test_leaf_up_delete_succeeds` |
| DL4 | Owned light rows auto-deleted | contacts / periods (and stakeholders etc.) soft-deleted with the entity | `_delete_auto_relations` | `EntityAutoDeleteTests.test_auto_created_period_is_soft_deleted_with_entity` · `test_owned_contact_soft_deleted_with_entity` |
| DL5 | Circular links deletable | mutually-linked person↔project entities both delete (auto relations break the cycle) | `_delete_auto_relations` | `CircularStakeholderTests.test_mutually_linked_entities_are_deletable` |
| DL6 | Name reusable after delete | soft-deleted name frees the live-only constraint | `unique_entity_name_live` | `EntityNameReuseAfterSoftDeleteTests.test_soft_deleted_name_can_be_reused` |

### 5.6 Immutability

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `entity_type` changed after save | `ImmutableMixin.save()` + `_immutable_fields` | no direct app_entity pinning test (gap) |
| `user` changed after save | `ImmutableMixin.save()` + `_immutable_fields` | no direct app_entity pinning test (gap) |

---

## 6. Consumers contract (cross-app)

- **Operations** treat `Entity` as source/destination/fund and consume `entity_type` + the `is_*` predicates (`is_person`, `is_project`, `is_virtual`, `is_internal`, `is_vendor`, `is_client`) in `clean_source`/`clean_destination`/`clean`; the virtual singletons (`SYSTEM`, `WORLD`) are the fixed counterparties of several operation types. Every operation spec in `docs/operations/` pins these branches.
- **Transactions** are written against `source`/`target` funds; balances (`balance_at`, payment types only) and obligations (`payables_at`/`receivables_at`, issuance/adjustment types) derive from them.
- **`Entity.can_pay`** exempts virtual and external (non-internal) funds from balance checks — the mechanism behind "external clients/vendors and world/system are never balance-blocked" in the operation specs.
- **Periods**: `Entity.save()` keeps each real entity's open `FinancialPeriod` in sync (create on activation, close on deactivation); world/system never have periods — see `docs/operations` §6 of any op spec and the period feature docs.
- **Inventory**: `entity_detail` reads `inventory_value(entity, today)`; products are scoped to project entities (blocking deletion until cleared — DL1).

---

## 7. View / UI contract

| Route (mounted at `/entities/`) | View | Method(s) | Purpose |
|----------------------------------|------|-----------|---------|
| `/entities/` | `EntityListView` | GET | searchable + filterable entity registry (type/deletion/activation/search) |
| `/entities/<int:pk>/` | `EntityDetailView` | GET | entity profile + financial summary + stakeholder/contact/category surfaces; redirect target for most entity flows |

- List defaults to live, active, non-virtual entities and excludes tombstones unless the `deletion=deleted` filter is used.
- Detail shows the current balance / payables / receivables / stock-value card and adapts the Edit link to `project_edit` vs `person_edit` by `entity_type`.
- Authentication: all pages require a logged-in user; unauthenticated requests are redirected to login.

---

## 8. Branch catalog (all possible branches)

- **create — validation:** type required (VC1) · system singleton (VC2) · world singleton (VC3) · virtual role-flag clearing (VC4) · live-name unique (VC5).
- **create — effects:** atomic persist (SC1) · type stored (SC2) · canonical virtual names (SC3) · flags/active applied (SC4) · open period created (SC5) · virtual no period (SC6).
- **update — validation:** entity_type immutable (EU1) · user immutable (EU2) · live-name unique on rename (EU3).
- **activate/deactivate:** close open period on deactivate (AC1) · open period on activate (AC2) · virtual unaffected (AC3) · inactive can't pay (AC4).
- **list:** base all_objects (LV1) · type (LV2) · deletion (LV3) · activation (LV4) · search (LV5) · combined (LV6) · context (LV7) · auth (LV8).
- **detail:** load/404 (DV1) · edit target (DV2) · financial summary (DV3) · stakeholders (DV4) · auth (DV5).
- **delete (admin):** blocked by financial dependents (DL1) · no partial auto-delete (DL2) · leaf-up (DL3) · auto-delete owned light rows (DL4) · circular links (DL5) · name reuse (DL6).

## 9. Test coverage matrix

| Area | Test class / method | Branch(es) |
|------|---------------------|------------|
| List GET | `EntityListViewTest` (`test_views_get_entity_list_view.py`) | LV8 + load |
| List — type filter | `EntityListFilterByTypeTest.test_filter_by_type_person` · `…_project` · `…_all_excludes_system_world` · `…_system_world` | LV2 |
| List — activation filter | `EntityListFilterByActivationTest.test_filter_by_activation_active` · `…_inactive` | LV4 |
| List — search | `EntityListSearchTest.test_search_by_partial_name` · `…_case_insensitive` · `…_returns_no_results` | LV5 |
| List — combined | `EntityListCombinedFiltersTest.test_filter_by_type_and_activation` · `…_type_and_search` · `…_all_filters_combined` | LV6 |
| List — context | `EntityListContextDataTest.test_context_contains_filter_values` · `…_search_query` | LV7 |
| Detail GET | `EntityDetailViewTest` (`test_views_get_entity_detail_view.py`): authorized · with_stakeholders · navigation_keeps_operations_and_periods_links · nonexistent_404 · unauthenticated_redirected · context_has_financial_summary · reflects_payables · reflects_stock_value · financial_summary_links_and_balance | DV1–DV5 |
| Create + period | `PersonCreateViewTest.test_person_create_creates_financial_period` | SC5 |
| Period sync | `FinancialPeriodEntityPeriodAutoCreateTest.test_world_entity_does_not_get_period` · `…_system_entity_does_not_get_period` | SC6 / AC3 |
| Soft-delete guard | `EntityGuardTests.test_delete_blocked_while_live_child_exists` · `test_auto_children_untouched_when_guard_blocks` · `test_leaf_up_delete_succeeds` · `test_get_delete_blockers_lists_dependents` | DL1–DL3 |
| Auto-delete | `EntityAutoDeleteTests.test_auto_created_period_is_soft_deleted_with_entity` · `test_owned_contact_soft_deleted_with_entity` | DL4 |
| Circular links | `CircularStakeholderTests.test_mutually_linked_entities_are_deletable` | DL5 |
| Name reuse | `EntityNameReuseAfterSoftDeleteTests.test_soft_deleted_name_can_be_reused` · `test_live_duplicate_name_still_rejected` | DL6 / VC5 |
| Name uniqueness (form) | `PersonCreateViewTest.test_person_create_invalid_duplicate_name` · `PersonEditViewTest.test_invalid_form_duplicate_name` · `ProjectEditViewTest.test_invalid_form_duplicate_name` | VC5 / EU3 |
| Derived financials (deep) | pinned across operation spec suites (`docs/operations`) and the entity-detail context tests above | §4 |

**Known coverage gaps (no direct `app_entity` pinning test):** type-required and singleton `clean()` errors (VC1–VC3), virtual role-flag clearing (VC4), canonical virtual names (SC3), `entity_type`/`user` immutability (EU1/EU2/§5.6), deactivate/activate period side effects (AC1/AC2).
