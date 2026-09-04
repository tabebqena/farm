# Contact Info — Entity Contract

**Epic:** Entity & Stakeholder Management — Relationships & Structure
**Area app:** `app_entity`
**Actions:** `add`, `edit (label/value/primary)`, `detail (via entity)`
**Contract status:** v1 (widened) — all branches recorded, business logic registered, test coverage mapped.

> **Primary source of contract.** This document is the authoritative contract for **ContactInfo** — the phone/email/address/website records attached to an `Entity` — and its add (`AddContactInfoView`) and edit (`EditContactInfoView`) views.
> Every clause below names its implementing code (model → view) and its pinning test — as plain names, never links, so renames do not break the spec.
> Where code and spec disagree, the spec states the *intended* behavior — fix the code, not the spec.
> ContactInfo rides on the shared Entity lifecycle (soft delete, PROTECT, detail). See the [Entity lifecycle](entity_1_lifecycle.md) contract for the shared foundation.

---

## 1. Identity

| Field | Value | Defined in |
|-------|-------|-----------|
| Model | `ContactInfo` (owner: `entity` FK → `Entity`, PROTECT, related `contacts`) | |
| Contact types | `TYPES` — `phone`, `email`, `address`, `website` | |
| Labels | `LabelTypes` — `work`, `personal`, `home` | |
| Fields | `contact_type`, `value`, `label`, `is_primary` (+ shared audit fields) | |
| Defaults | `is_primary=False` | |
| Set-on-create, never exposed for edit | `entity`, `contact_type` | |
| Add view | `AddContactInfoView` (`<entity_id>/contact/add/` → `add_contact_info`) | |
| Edit view | `EditContactInfoView` (`contact/<int:pk>/edit/` → `edit_contact_info`) | |
| Template | `app_entity/contact_form.html` (shared add/edit) | |
| Soft-delete | auto soft-deleted with the owning entity (`Entity._delete_auto_relations` → `contacts`) | |

---

## 2. Registered business logic (contract map)

### 2.1 Model / domain layer

| Concern | Implementing code |
|---------|-------------------|
| `ContactInfo` model + `TYPES` / `LabelTypes` choice sets | |
| Live audit on save | `ContactInfo.save()` |
| Owner deletability (auto soft-delete) | `Entity._delete_auto_relations` (`contacts`) |

### 2.2 View / UI layer

| Concern | Implementing code |
|---------|-------------------|
| Add (GET empty form / POST atomic create) | `AddContactInfoView` |
| Edit (GET prefilled / POST update + primary demotion) | `EditContactInfoView` |
| Redirect target | `entity_detail` (owning entity) |
| Lookup helper (custom 404 message) | `get_object_or_404` (farm shortcut) |

### 2.3 Tests

| Concern | Test file |
|---------|-----------|
| Auto soft-delete with owning entity | `app_entity.tests.test_soft_delete_guard` (`EntityAutoDeleteTests`) |
| Contact surface on entity detail | (template/regression — no dedicated `app_entity` view test today; gap) |

---

## 3. Domain model & invariants

- A `ContactInfo` belongs to exactly one `Entity` (`entity` FK, PROTECT). `contact_type` is one of phone/email/address/website; `label` is work/personal/home; `value` is the free-text detail; `is_primary` flags the preferred record.
- **Ownership immutability is UI-level, not model-level.** `entity` and `contact_type` are fixed at creation and the edit view never exposes them — but `ContactInfo` declares no `_immutable_fields`, so the model itself does not enforce immutability (the class docstring's "values are immutable once saved" overstates the code; `value`/`is_primary`/`label` are explicitly editable).
- **Single-primary invariant.** The intended behavior is *at most one primary contact per entity*. The **edit** flow enforces it by demoting every other primary of the entity when the edited record is flagged primary. The **add** flow does **not** demote, so adding a second primary while one already exists is currently possible — registered as a gap (§8).
- Contact rows are owned light rows: they are auto soft-deleted when their entity is deleted, so they never block the entity's delete guard.

---

## 4. Derived financial contract

`N/A` — contact info carries no balance and no financial effect.

---

## 5. Actions

### 5.1 `add` — `AddContactInfoView` (GET/POST `<entity_id>/contact/add/`)

#### 5.1.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CI1 | Owning entity exists + live | entity pk resolves to a live `Entity` | 404 (custom message) | `"Entity not found or has been deleted."` | `get_object_or_404` | no direct pinning test (gap) |
| CI2 | Choices valid | `contact_type` ∈ `TYPES`, `label` ∈ `LabelTypes`, `value` non-empty | `ValidationError` on create (caught → re-render with error message) | `"Error: …"` | `ContactInfo` field choices + `CharField` validators | no direct pinning test (gap) |

#### 5.1.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CI3 | Contact created | `ContactInfo.objects.create(entity, contact_type, label, value, is_primary)` inside atomic | `AddContactInfoView.post` | no direct pinning test (gap) |
| CI4 | Audit + message + redirect | `contact_info_added` audit, success message, redirect `entity_detail` | `AddContactInfoView.post` | no direct pinning test (gap) |

### 5.2 `edit` — `EditContactInfoView` (GET/POST `contact/<int:pk>/edit/`)

#### 5.2.1 Validation branches

| # | Branch | Pass condition | Failure outcome | Error (on failure) | Enforced by | Pinned by test |
|---|--------|----------------|-----------------|--------------------|-------------|----------------|
| CE1 | Contact exists + live | pk resolves to a live `ContactInfo` | 404 (custom message) | `"Contact information not found or has been deleted."` | `get_object_or_404` | no direct pinning test (gap) |

#### 5.2.2 Success effects

| # | Effect | Detail / invariant | Implemented by | Verified by |
|---|--------|--------------------|----------------|-------------|
| CE2 | Only label/value/primary edited | `contact_type` and `entity` unchanged (never read from POST) | `EditContactInfoView.post` | no direct pinning test (gap) |
| CE3 | Primary demotion | when `is_primary=True`, every other primary of the entity is set `False` (same atomic block) | `EditContactInfoView.post` | no direct pinning test (gap) |
| CE4 | Audit + message + redirect | `contact_info_updated` audit, success message, redirect `entity_detail` | `EditContactInfoView.post` | no direct pinning test (gap) |

### 5.3 `detail`

Contacts render on the shared `EntityDetailView` through the `contacts` reverse relation (no dedicated view). See [Entity lifecycle](entity_1_lifecycle.md) §5.4.2.

### 5.4 Deletion policy

No contact delete UI exists; a contact is removed by deactivating nothing (no `active` flag) — it is either left in place or removed through the admin/auto-delete path. Deleting the owning entity auto soft-deletes its contacts.

---

## 6. Consumers contract (cross-app)

- `Entity.contacts` is read by the entity detail template to render the contact list.
- No operation or transaction reads `ContactInfo`; it is pure address-book metadata. The only hard coupling is the auto soft-delete on the owner (`Entity._delete_auto_relations` → `contacts`).

---

## 7. View / UI contract

| Route (mounted at `/entities/`) | View | Method(s) | Purpose |
|----------------------------------|------|-----------|---------|
| `/entities/<int:entity_id>/contact/add/` | `AddContactInfoView` | GET/POST | attach a new contact record to an entity |
| `/entities/contact/<int:pk>/edit/` | `EditContactInfoView` | GET/POST | edit a contact's label/value/primary flag |

- `contact_form.html` renders the `TYPES` and `LabelTypes` choice sets in add mode and prefills them in edit mode (`is_edit=True`).
- The edit form does **not** include `entity` or `contact_type` controls; only `label`, `value` and `is_primary` are posted.
- Success (add or edit) redirects to the owning entity's `entity_detail`.

---

## 8. Branch catalog (all possible branches)

- **add — validation:** entity 404 (CI1) · choice/value validation (CI2).
- **add — effects:** create (CI3) · audit+message+redirect (CI4).
- **edit — validation:** 404 (CE1).
- **edit — effects:** label/value/primary only (CE2) · primary demotion (CE3) · audit+message+redirect (CE4).
- **invariant:** at most one primary per entity (enforced on edit; **not** enforced on add — gap).

## 9. Test coverage matrix

| Area | Test class / method | Branch(es) |
|------|---------------------|------------|
| Auto soft-delete | `EntityAutoDeleteTests.test_owned_contact_soft_deleted_with_entity` | §3 / §5.4 |

**Known coverage gaps:** there is **no dedicated `app_entity` test** for the contact add/edit views or the model — CI1–CI4 and CE1–CE4 are all unpinned, and the single-primary invariant is untested. The add-flow non-demotion (possible second primary) is a behavior gap to close (either demote on add or add a partial unique constraint).
