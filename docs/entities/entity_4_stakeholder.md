# Stakeholder — Entity Contract

**Epic:** Entity & Stakeholder Management — Relationships & Structure
**Area app:** `app_entity`
**Actions:** `add (per role: vendor/client/worker/shareholder)`, `edit (notes/active)`, `deactivate (active)`, `detail (via entity)`
**Contract status:** v1 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **Stakeholder** link — the row that says *person P acts as role R in parent project/entity E* — plus its add views (`AddStakeholderView` and the `AddVendorView` / `AddClientView` / `AddWorkerView` / `AddShareholderView` subclasses) and its edit view (`EditStakeholderView`).
> Every clause below names its implementing code (model → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> Stakeholders are the connective tissue operations consume — the vendor/client/worker/shareholder pickers of Purchase, Sale, Worker Advance, Project Funding and Refund are built from **active** stakeholder links. Those consumers are pinned in the operation specs; this contract pins the shape the views must create.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Model | `Stakeholder` | |
| Role choice-set | `StakeholderRole` — `WORKER`, `CLIENT`, `VENDOR`, `SHAREHOLDER` | |
| Parties | `parent` (owner; FK → `Entity`, PROTECT, related `stakeholders`) · `target` (member; FK → `Entity`, PROTECT, related `memberships`) | |
| Mutable fields | `notes`, `active` | |
| Immutable fields | `parent`, `target`, `role` (via `_immutable_fields`) | |
| Defaults | `active=True` | |
| Admin | `StakeholderClass` (registered `Stakeholder`) — admin-only delete | |
| Soft-delete | auto-deleted when either party is deleted (via `Entity._delete_auto_relations` → `stakeholders`/`memberships`) | |
| Add views | `AddVendorView` (`project/<pk>/add-vendor/`) · `AddClientView` (`…/add-client/`) · `AddWorkerView` (`…/add-worker/`) · `AddShareholderView` (`…/add-shareholder/`) | |
| Edit view | `EditStakeholderView` (`stakeholder/<int:pk>/edit/` → `edit_stakeholder`) | |
| Template | `app_entity/stakeholder_form.html` (shared add/edit) | |

---

## 2. Registered business logic (contract map)

### 2.1 Model / domain layer

| Concern | Implementing code |
|---------|-------------------|
| `Stakeholder` model + `StakeholderRole` choices + `clean()` party/role rules | |
| Immutability of `parent`/`target`/`role` | `_immutable_fields` on `Stakeholder` |
| Live audit on save | `Stakeholder.save()` |
| Party deletability (auto soft-delete both directions) | `Entity._delete_auto_relations` (`stakeholders`, `memberships`) |

### 2.2 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Add base + role subclasses | `AddStakeholderView` + `AddVendorView` / `AddClientView` / `AddWorkerView` / `AddShareholderView` |
| Role eligibility filter | `_role_filter` |
| Parent (internal project) guard | `_load_parent` (requires `is_internal`) |
| Target active guard | `_load_target` (requires `active`) |
| Role/target validation | `_validate_role_target` |
| Create-or-fetch + audit | `_create_stakeholder` (via `Stakeholder.objects.get_or_create`) |
| Edit (notes/active only) | `EditStakeholderView` |
| Redirect target | `entity_detail` (parent pk) |

### 2.3 Cross-app consumers

| Concern | Consumer |
|---------|----------|
| Active `VENDOR` stakeholder → Purchase destination picker + `clean_destination` | `op_9_purchase` |
| Active `CLIENT` stakeholder → Sale source picker | `op_10_sale` |
| Active `WORKER` stakeholder → Worker Advance destination picker + `clean_destination` | `op_7_worker_advance` |
| Active `SHAREHOLDER` stakeholder → Project Funding/Refund picker + `clean` | `op_3_project_funding` / `op_4_project_refund` |
| Stakeholder list shown on entity detail | `EntityDetailView` |

### 2.4 Tests

| Concern | Test file |
|---------|-----------|
| Add-stakeholder flow (role filters, GET, POST, guards) | `app_entity.tests.test_add_stakeholder_view` |
| Entity auto-delete of stakeholder/membership links | `app_entity.tests.test_soft_delete_guard` (`CircularStakeholderTests`) |
| Detail loads stakeholders | `app_entity.tests.test_views_get_entity_detail_view` |

---

## 3. Domain model & invariants

- A `Stakeholder` links a **project/person** `parent` to a **person/project** `target` under a single immutable `role`. Both parties must be `PERSON` or `PROJECT` entities; virtual (`SYSTEM`/`WORLD`) parties are rejected by `clean()`.
- `parent`, `target` and `role` are **immutable** after save (`_immutable_fields`); only `notes` and `active` change — and the edit view updates exactly those two.
- Role/party compatibility (`Stakeholder.clean()`):
  - `parent` must be person/project (`"The parent party should be a project or person entity."`).
  - `target` must be person/project (`"The target party should be a project or person entity."`).
  - A **project** `target` may not carry the `worker` or `shareholder` role (`"The target party (project) can't be assigned as a worker or a shareholder."`).
- The default `active=True` matters: operations only accept **active** stakeholder links, and the add flow creates links active by default. There is no hard delete UI — a link is deactivated (`active=False`) or soft-deleted through the admin/auto-delete path.
- Because both parties hold PROTECT FKs to `Entity`, `Entity._delete_auto_relations` lists `stakeholders` (parent side) **and** `memberships` (target side), so deleting an entity auto soft-deletes its links — which is what makes mutually-linked person↔project entities deletable.

---

## 4. Derived financial contract

`N/A` — a stakeholder link itself carries no balance. Its financial relevance is indirect: the active link gates the operation flows that do move money (see §6).

---

## 5. Actions

### 5.1 `add` (per role) — `AddStakeholderView` subclasses

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| SA1 | Parent is an internal project | `parent.is_internal` and entity exists | 404 (message + audit) | `"Project not found or is not configured as internal."` | `_load_parent` | `AddStakeholderViewTest.test_post_non_internal_parent_returns_404` |
| SA2 | Target exists + active | target resolves and is `active` | 404 (message) | `"Entity not found or is not active."` | `_load_target` | `AddStakeholderViewTest.test_post_missing_target_returns_404` |
| SA3 | Worker/Shareholder target is a person | `target.is_person` | re-render with error (empty dropdown) | `"Only People can be assigned as Workers."` / `"…as Shareholders."` | `_validate_role_target` | `AddStakeholderViewTest.test_post_non_person_worker_rerenders_with_error` |
| SA4 | Vendor target is configured vendor | `target.is_vendor` | re-render with error | `"<target> is not configured as a Vendor."` | `_validate_role_target` | `AddStakeholderViewTest.test_post_non_vendor_target_rerenders_with_error` |
| SA5 | Client target is configured client | `target.is_client` | re-render with error | `"<target> is not configured as a Client."` | `_validate_role_target` | no direct pinning test (gap) |
| SA6 | Model party/role clean | parties are person/project and project-target not worker/shareholder | `ValidationError` on save | model messages (§3) | `Stakeholder.clean()` | no direct `app_entity` pinning test (gap; reached via view validation first) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SA7 | Link created active | `Stakeholder(parent=project, target=target, role=role)` with `active=True` | `_create_stakeholder` (`get_or_create`) | `AddStakeholderViewTest.test_post_creates_stakeholder_and_redirects` |
| SA8 | Duplicate is idempotent | re-adding the same (parent, target, role) reuses the existing row | `Stakeholder.objects.get_or_create` | `AddStakeholderViewTest.test_post_duplicate_does_not_create_second_row` |
| SA9 | GET lists only eligible targets | available = live entities matching the role filter (`is_vendor`/`is_client`/`is_worker`/`is_shareholder` + `active`), excluding the parent; unknown role → empty | `get()` + `_role_filter` | `test_get_renders_only_eligible_vendors` · `test_get_filters_each_role` · `test_get_unknown_role_renders_empty_dropdown` |
| SA10 | Success message + redirect | `stakeholder_created`/`stakeholder_already_exists` audit, message, redirect `entity_detail` (parent) | `_create_stakeholder` | `test_post_creates_stakeholder_and_redirects` |

### 5.2 `edit` — `EditStakeholderView` (`stakeholder/<int:pk>/edit/`)

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| SE1 | Link exists + live | pk resolves to a live `Stakeholder` | 404 (message) | `"Stakeholder relationship not found or has been deleted."` | `get_object_or_404` | no direct pinning test (gap) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SE2 | Only notes/active changed | `notes` + `active` updated; `parent`/`target`/`role` untouched (immutable) | `EditStakeholderView.post` | no direct pinning test (gap) |
| SE3 | Audit + message + redirect | `stakeholder_updated` audit, message, redirect `entity_detail` (parent) | `EditStakeholderView.post` | no direct pinning test (gap) |

### 5.3 `deactivate`

The edit view's `active` checkbox (or admin) is the sanctioned way to remove a link from circulation — there is no hard-delete UI. Operations that require an **active** stakeholder then reject the link.

### 5.4 Immutability

| Branch | Enforced by | Pinned by test |
|--------|-------------|----------------|
| `parent` changed after save | `ImmutableMixin.save()` + `_immutable_fields` | no direct app_entity pinning test (gap) |
| `target` changed after save | same | no direct app_entity pinning test (gap) |
| `role` changed after save | same | no direct app_entity pinning test (gap) |

---

## 6. Consumers contract (cross-app)

Every consumer reads **active** `Stakeholder(parent=project, target=<party>, role=<R>)` rows:

| Role | Consumed by | Shape required |
|------|-------------|----------------|
| `VENDOR` | Purchase (`op_9`) | destination must be an active vendor stakeholder of the source project |
| `CLIENT` | Sale (`op_10`) | source picker lists active client stakeholders of the project |
| `WORKER` | Worker Advance (`op_7`) | destination must be an active worker stakeholder of the source project |
| `SHAREHOLDER` | Project Funding (`op_3`) / Project Refund (`op_4`) | the URL person must be an active shareholder of the destination/source project |

The operation specs pin each consumer branch (e.g. Purchase `VC4`, Worker Advance `VC3`, Funding `VC16`). This contract is the *producer* side: the add views must create exactly those links with `active=True`, `parent=project`, `role=<role>`.

---

## 7. View / UI contract

| Route (mounted at `/entities/`) | View | Method(s) | Purpose |
|----------------------------------|------|-----------|---------|
| `/entities/project/<int:pk>/add-vendor/` | `AddVendorView` | GET/POST | add a VENDOR link to the project |
| `/entities/project/<int:pk>/add-client/` | `AddClientView` | GET/POST | add a CLIENT link |
| `/entities/project/<int:pk>/add-worker/` | `AddWorkerView` | GET/POST | add a WORKER link |
| `/entities/project/<int:pk>/add-shareholder/` | `AddShareholderView` | GET/POST | add a SHAREHOLDER link |
| `/entities/stakeholder/<int:pk>/edit/` | `EditStakeholderView` | GET/POST | edit notes + active |

- The add form (`stakeholder_form.html`) renders an eligible-entity dropdown driven by the role filter; on validation failure it re-renders with an empty dropdown and a `"Configuration Error"` message.
- The edit form is the same template in edit mode (`is_edit=True`) and exposes only `notes` and `active`.
- All add routes require the parent to be an **internal** project; success always redirects to that project's `entity_detail`.

---

## 8. Branch catalog (all possible branches)

- **add — validation:** internal parent (SA1) · target active/exists (SA2) · worker/shareholder person-only (SA3) · vendor configured (SA4) · client configured (SA5) · model party/role clean (SA6).
- **add — effects:** link created active (SA7) · idempotent duplicate (SA8) · eligible GET list / empty for unknown role (SA9) · audit+message+redirect (SA10).
- **edit — validation:** 404 (SE1).
- **edit — effects:** notes/active only (SE2) · audit+message+redirect (SE3).
- **immutability:** parent/target/role frozen after save (§5.4).

## 9. Test coverage matrix

| Area | Test class / method | Branch(es) |
|------|---------------------|------------|
| Role filter map | `AddStakeholderViewTest.test_role_filter_maps_known_roles` · `test_role_filter_unknown_role_returns_none` | SA9 |
| GET eligibility | `AddStakeholderViewTest.test_get_renders_only_eligible_vendors` · `test_get_filters_each_role` · `test_get_unknown_role_renders_empty_dropdown` | SA9 |
| POST create | `AddStakeholderViewTest.test_post_creates_stakeholder_and_redirects` | SA7, SA10 |
| POST idempotent | `AddStakeholderViewTest.test_post_duplicate_does_not_create_second_row` | SA8 |
| POST validation | `AddStakeholderViewTest.test_post_non_person_worker_rerenders_with_error` · `test_post_non_vendor_target_rerenders_with_error` | SA3, SA4 |
| POST guards | `AddStakeholderViewTest.test_post_non_internal_parent_returns_404` · `test_post_missing_target_returns_404` | SA1, SA2 |
| Auto-delete / circular | `CircularStakeholderTests.test_mutually_linked_entities_are_deletable` | §3 soft-delete invariant |
| Detail list | `EntityDetailViewTest.test_entity_detail_with_stakeholders` | §7 |
| Operation consumers | purchase/sale/worker-advance/funding create suites (see `docs/operations`) | §6 |

**Known coverage gaps (no direct `app_entity` pinning test):** client-target validation (SA5), model `clean()` party/role branches (SA6), edit view 404/update/audit (SE1–SE3), and the parent/target/role immutability guard (§5.4). The add flow is well covered; the edit flow and model-level clean are not.
