# `<AREA_NAME>` — Entity Contract

<!--
Template for an entity-area spec written as a primary-source contract.

The entity specs live under docs/entities/ and mirror the structure and intent
of the operation contracts under docs/operations/ (see the operation template
`docs/operations/_OPERATION_SPEC_TEMPLATE.md`). They are NOT a restatement of a
single money-moving operation; they pin the `app_entity` domain — the "who" and
the structural scaffolding (Entity types & lifecycle, Person, Project & setup
wizard, Stakeholder, ContactInfo, FinancialCategory) — that every operation and
transaction consumes.

Steps to write / widen an entity area:
  1. Read the area's models (apps/app_entity/models) — record every model,
     field, choice-set, manager, immutability rule, uniqueness constraint and
     domain `clean()`/`save()` hook into §1 (identity) and §2.1/§2.2 (map).
  2. Read the shared app_base machinery the models rely on (BaseModel soft
     delete + delete guard, SafeQuerySet/ActiveManager, ImmutableMixin,
     BaseModel.delete admin-only policy) and register it in §2.2.
  3. Read the area's views, forms, templates, URL wiring and admin registration
     to register the view contract (§2.4/§2.5) and §7.
  4. Read the cross-app consumers (operations, transactions, reports) that
     depend on the area's models and record the consumed shape in §6
     (consumers contract). For example entity lifecycle is consumed by every
     operation spec; stakeholder relationships are consumed by Purchase, Sale,
     Worker Advance, Project Funding/Refund.
  5. Read the area's tests and map every branch to a pinning test in §9. Where
     a branch has no pinning test, write `no pinning test (gap)` — the spec is
     the primary source, so a gap is a record of missing coverage, not an
     excuse to soften the stated branch.
  6. Record every implementing concern in §2 (contract map). The spec is the
     primary source of contract: where code and spec disagree, fix the code,
     not the spec.
  7. Reference code and tests by plain name only — never as markdown links (no
     `[symbol](path)` and no `file.py:NN`), so renames do not break the spec.
-->

**Epic:** `<ENTITY EPIC>` — `<SECTION>`
**Area app:** `app_entity`
**Actions:** `<comma-separated: create, edit/update, activate, deactivate, list, detail, delete (admin), reverse, add/remove link, assign>`
**Contract status:** v1 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for the **`<AREA_NAME>`** area of the entity app.
> Every clause below names its implementing code (model → base machinery → consumer → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> The entity-area specs share this structure — see [`_ENTITY_SPEC_TEMPLATE.md`](_ENTITY_SPEC_TEMPLATE.md) — and build on the
> [Entity lifecycle](entity_1_lifecycle.md) contract for the shared `Entity`/soft-delete/derived-financial foundation.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Model(s) | `<Model>`, `<Related>` | |
| Role / choice-set | `<EntityType.X>`, `<StakeholderRole.Y>`, `<TYPE>` | |
| Managers | `objects` (live only) / `all_objects` (incl. soft-deleted) | |
| Immutable fields | `<field(s)>` via `_immutable_fields` | |
| Uniqueness (live-only) | `<constraint name>` | |
| Admin | `<Admin>` registration (admin-only delete) | |
| Soft-delete relations | `<_delete_auto_relations>` (auto) / others (guard-blocked) | |

---

## 2. Registered business logic (contract map)

The tables below **register every file that implements this area**. The spec is the primary source of contract; each row names the code that must honor it (plain names, no links).

### 2.1 Model / domain layer

| Concern | Implementing code |
|---------|-------------------|
| Models + field/choice definitions | |
| Domain `clean()` / `save()` / `create()` rules | |
| Managers / querysets | |
| Derived properties | |

### 2.2 Shared base layer (`app_base`)

| Concern | Implementing code |
|---------|-------------------|
| Soft-delete + delete guard (live dependents block; `_delete_auto_relations` auto-delete) | `BaseModel` |
| Live-only manager + blocked bulk writes | `ActiveManager` / `SafeQuerySet` / `DefaultManager` |
| Immutability on save | `ImmutableMixin` |
| Audit fields (`created_at` / `updated_at` / `deleted_at`) | `BaseModel` |
| Audit logging | `audit_logger` / `logger` |

### 2.3 Cross-app consumers

| Concern | Consumer |
|---------|----------|
| (what downstream code depends on this area) | `app_operation`, `app_transaction`, `app_inventory`, `app_adjustment`, `app_report` … |

### 2.4 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Create / edit views | |
| List / detail views | |
| Domain action views | |
| Type/role guards | |
| URLs | |
| Templates | |
| Forms | |

### 2.5 Tests

| Concern | Test file |
|---------|-----------|
| `<action>` branches | |
| Coverage manifest | |

---

## 3. Domain model & invariants

(Describe the area's entities/records, their relationships, and the invariants that hold: uniqueness, immutability, mandatory role flags, virtual/singleton rules, soft-delete/PROTECT semantics.)

---

## 4. Derived financial contract

(Only where the area feeds derived balances — see the lifecycle contract §4. State the derivation and any project-only / virtual exemptions. For structural areas write `N/A — see lifecycle contract §4`.)

---

## 5. Actions

### 5.1 `create` (domain / view)

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| VC1 | … | … | `ValidationError` / message / redirect | `"…"` | `code` | `test` |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| SC1 | … | … | `code` | `test` |

### 5.2 `edit` / `update`

(validation branches + success effects, as §5.1; record what is mutable vs immutable, and any exclusive-owner demotion rules.)

### 5.3 `activate` / `deactivate`

(only where activation is a real action with side effects — e.g. the open financial-period sync in `Entity.save()`.)

### 5.4 `list` / `detail`

(GET contracts: filters, default scope, context, navigation, permission behavior.)

### 5.5 `delete` (admin-only)

`Model.delete()` is a soft delete, and per project policy it is an **admin-only** action — the project UI must never surface a view/form/button that calls it. Record the guard branches and which live dependents block vs auto-delete.

### 5.6 Immutability

`<field>` cannot change after save — enforced by `ImmutableMixin._immutable_fields`. Record each immutable field and its pinning test.

---

## 6. Consumers contract (cross-app)

(What downstream code requires from this area and the exact shape it consumes — with plain references to the consuming operation/feature specs.)

## 7. View / UI contract

(route, filters, pickers, type guards, permission behavior, redirect targets, templates.)

---

## 8. Branch catalog (all possible branches)

- **create — validation:** …
- **create — effects:** …
- **edit — validation:** …
- **edit — effects:** …
- **activate / deactivate / list / detail / delete / domain actions:** …

## 9. Test coverage matrix

| Area | Test class / method | Branch(es) |
|------|---------------------|------------|
| … | `test…` | … |
