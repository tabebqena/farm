# Plan — Guard parents with live children from soft deletion

Status: in progress (guard deferred by owner — schema pre-work merged first)
Related: soft-delete migration (conditional unique indexes), `BaseModel.delete()`
soft-delete semantics.

## Implemented (committed)

Schema pre-work requested before the guard:

- `on_delete=CASCADE` → `PROTECT` (`6c969e5`): InvoiceItem.operation,
  Transaction.content_type, InvoiceItemAdjustmentLine.adjustment,
  Stakeholder.parent/target, FinancialCategoriesEntitiesRelations.entity/.category.
- `on_delete=SET_NULL` → `PROTECT` (`455cc39`): InvoiceItemAdjustment.adjustment,
  MedicalRecord.officer, ProductTemplate.gives_birth_to, Product.mother,
  Transaction.reversal_of.

Now every FK is `PROTECT`, so the guard's relation filter simplifies to "any
reverse FK/O2O whose `on_delete` is not SET_NULL/SET_DEFAULT" (only PROTECT
remains in the schema today). Confirmed via introspection that reverse rel
`on_delete` lives at `rel.field.remote_field.on_delete`.

## Guard implemented

Implemented the parent-with-children guard in `BaseModel.delete()`:

- Refuses to soft-delete a live parent with live dependents; raises a
  `ValidationError` (`code="delete_blocked"`) naming what to delete/reverse
  first. `get_delete_blockers()` exposes the same labels.
- Per-model config: `_delete_auto_relations` (reverse accessor names whose live
  dependents are AUTO soft-deleted instead of blocking — the circularity
  breaker) and `_delete_guard_ignore_relations` (ignore entirely).
- Whole delete is transactional and re-entrancy safe (`_DELETE_IN_PROGRESS`).
- `Entity` declares auto relations for owned light rows (contacts,
  stakeholders, memberships, category relations, financial periods); products /
  operations / transactions still block.
- Tests in `apps/app_entity/tests/test_soft_delete_guard.py`.

## Problem

Since [`BaseModel.delete()`](apps/app_base/models.py:153) only stamps
`deleted_at`, deleting a parent never cascades and never raises
`ProtectedError`. Live dependent rows keep their FK and silently point at a
now-hidden parent (a state the earlier analysis flagged as Risk 2). The
request: **refuse to soft-delete a parent that still has live child rows and
tell the caller which records to delete/remove first.**

## Design

### 1. Central guard in `BaseModel`

Add a private helper on [`BaseModel`](apps/app_base/models.py:73) that lists
live dependents, and call it at the top of [`BaseModel.delete()`](apps/app_base/models.py:153)
before stamping `deleted_at`. Because every delete (direct `obj.delete()`,
[`SafeQuerySet.delete()`](apps/app_base/managers.py:49) per-row loop, admin)
reaches this method, the guard covers the whole delete surface with one change.

Behavior:
- Only guard when `self.pk` is set and the row is **live** (`deleted_at` unset)
  — re-deleting an already-soft-deleted row stays a no-op.
- Consider reverse relations where the child holds a real FK/OneToOne to this
  parent with `on_delete` in `(CASCADE, PROTECT)`:
  - Iterate `self._meta.get_fields()`; keep `auto_created` relations that are
    `one_to_many` or `one_to_one` (reverse FK / reverse O2O).
  - Drop `SET_NULL` / `SET_DEFAULT` relations (optional references — not
    dependents the user must delete first).
  - Reverse **M2M with an explicit through** is covered via the through model's
    FK to the parent; **auto-created M2M** join rows are deliberately out of
    scope (documented boundary).
- Count only **live** children: if the child model has `deleted_at`, filter
  `deleted_at__isnull=True`; otherwise count all rows (e.g. `auth.User`).
- Aggregate by child model into human labels such as
  `"3 transactions (incoming/outgoing)"`, `"2 products"`, `"1 contact info"`.
- Raise `ValidationError` (`code="delete_blocked"`) shaped as:
  `<Model> cannot be deleted because it still has live related records:
  <list>. Delete or reverse those first, then try again.`

New public helpers:
- `get_delete_blockers() -> list[str]` — reusable list of human labels (used by
  the guard and available to admin/views).
- Class-level overrides for any relation that must never block, e.g.
  `_delete_guard_skip_relations = {"related_name_a", ...}` — empty by default.

### 2. Admin error surfacing

Django admin already refuses deletes on the confirmation page for `PROTECT`-
declared relations (collector fills `protected` and `_delete_view` shows
"Cannot delete ... protected foreign keys"). The gap is parents whose children
are `CASCADE`-declared (e.g. `Stakeholder.parent` → Entity): the confirm page
lists them as "to be deleted", the user confirms, and our guard raises — which
would otherwise surface as a 500.

Add a small reusable mixin (new module `apps/app_base/admin_guard.py`) that
overrides `delete_model()` / `response_delete()` to catch the guard's
`ValidationError` and `message_user(..., level=ERROR)` then redirect back to the
changelist. Apply it to the delete-capable admin classes:

- `EntityClass`, `StakeholderClass` (app_entity/admin.py)
- `ProductTemplateAdmin`, `ProductAdmin`, `ProductCapitalValuationAdmin`
  (app_inventory/admin.py)
- `TransactionAdmin` (app_transaction/admin.py)
- `AdjustmentAdmin` (app_adjustment/admin.py)
- `FinancialPeriodAdmin` (app_operation/admin.py)
- `MedicalRecordAdmin` (app_animal/admin.py)

### 3. Tests (new `apps/app_entity/tests/test_delete_guard.py`)

Using real models to pin behavior:
- Entity with a live child (`ContactInfo` PROTECT, `Stakeholder` CASCADE, or a
  `FinancialCategoriesEntitiesRelations` row) → `delete()` raises
  `ValidationError`; message names the child type and says to delete it first;
  row still live.
- Soft-delete the child first → parent deletion then succeeds (walk the tree).
- Bare parent (no children) still soft-deletes; already-deleted row re-delete
  stays a no-op.
- A child model without `deleted_at` (e.g. `auth.User` via `Entity.user`)
  still blocks while the row exists.
- Queryset path: `Parent.all_objects.filter(...).delete()` also blocked for a
  parent with live children.

### 4. Housekeeping

- `CHANGES.md` entry + `VERSION` patch bump.
- Commit after implementation and green tests.
