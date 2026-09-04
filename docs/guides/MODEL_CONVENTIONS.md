# Model Conventions — soft delete & `on_delete=PROTECT`

This document explains the project's model conventions around deletion. It is
the canonical reference for the mandatory rule stated in
[`AGENTS.md`](../../AGENTS.md): **every new relationship must use
`on_delete=models.PROTECT`**.

---

## 1. Why the project only soft-deletes

Every record in the system inherits from
[`BaseModel`](../../apps/app_base/models.py), which provides the soft-delete
column `deleted_at`:

- [`BaseModel.delete()`](../../apps/app_base/models.py) **never removes a row**.
  It stamps `deleted_at = now` and re-saves, so the row stays in the table for
  the audit trail and can be restored later by clearing `deleted_at`.
- [`BaseModel.save()`](../../apps/app_base/models.py) runs `full_clean()`, so
  every save — including a soft delete — is validated.
- The default managers mirror this:
  - `objects` ([`ActiveManager`](../../apps/app_base/managers.py)) hides
    soft-deleted rows (`deleted_at IS NULL`).
  - `all_objects` (unfiltered) keeps every row reachable, tombstones included.
- Bulk writes are restricted by [`SafeQuerySet`](../../apps/app_base/managers.py)
  — bulk `update`/`bulk_create` are blocked and queryset `delete()` soft-deletes
  row by row.

Because deletes are always `UPDATE`s, **Django's `on_delete` behavior is never
triggered**: nothing cascades, nothing is set to NULL, and no `ProtectedError`
is raised by the database layer. Those declarations exist purely for schema
semantics and for Django admin's delete-confirmation logic.

---

## 2. The rule (mandatory)

> Every new relationship — `models.ForeignKey`, `models.OneToOneField`, and the
> `models.ForeignKey` fields of any many-to-many `through` model — **MUST**
> declare `on_delete=models.PROTECT`.

> Do **NOT** use `on_delete=models.CASCADE`, `SET_NULL`, or `SET_DEFAULT` in
> new code.

> `null=True` stays allowed for optional relationships. **Optionality is
> expressed by nullability, never by `SET_NULL`.**

### Good

```python
entity = models.ForeignKey(
    "Entity",
    on_delete=models.PROTECT,   # required
    related_name="invoices",
)

# Optional relationship: still PROTECT; nullability expresses "not set".
officer = models.ForeignKey(
    User,
    on_delete=models.PROTECT,   # required
    null=True,
    blank=True,
)
```

### Bad

```python
entity = models.ForeignKey("Entity", on_delete=models.CASCADE, ...)  # never fire
officer = models.ForeignKey(User, on_delete=models.SET_NULL, ...)    # never fires
```

---

## 3. Why `PROTECT`

1. **Declarations must match reality.** Soft delete means `CASCADE` and
   `SET_NULL` can never run. Declaring them is misleading: Django admin would
   offer to "delete related objects" or "set related objects to null", and
   future hard-delete code would get behavior nobody planned for.

2. **Dependents stay visible and protected.** With `PROTECT`, a parent that has
   live children is treated as undeletable — Django admin's delete-confirmation
   page lists the protected rows, and any code path that tries to remove the
   parent gets a clear signal. This keeps the audit trail intact: children are
   never silently swept away.

3. **Uniform, predictable semantics.** Every FK behaves the same way. There is
   no split between "owned children that vanish" and "optional links that
   disappear" — which would be doubly dangerous under a system where neither
   effect can actually happen.

4. **Leaf-up deletion.** To delete a parent you first delete (soft) — or
   reverse — its dependents, one level at a time. This is the intended,
   audited workflow and mirrors the DB `PROTECT` semantics the schema now
   declares everywhere.

---

## 4. How deletion actually works

To remove a record:

1. Remove (soft-delete) or reverse its dependents first, deepest first.
2. Then call `obj.delete()` (or filter through `all_objects` and delete) — this
   only stamps `deleted_at`.
3. To undo a mistake, clear `deleted_at` and `save()` to restore the row.

Do not write code that relies on cascade-removal or null-out side effects: they
will never run. If a workflow genuinely needs to "detach" an optional link, set
the field to `None` and `save()` explicitly in the view/model logic — that is
an application decision, not an `on_delete` decision.

---

## 5. Exceptions

None by default. Legacy or unchanged schema fields that already use
`CASCADE`/`SET_NULL` are left as-is (they are migrated toward `PROTECT`
incrementally and never fire anyway). Any genuinely justified deviation in
**new** code must be discussed with the maintainer and accompanied by an
explicit rationale before it is merged.

---

## 6. Quick verification

A reviewer (or agent) can scan for violations with a project-wide grep on the
current model sources:

```bash
# Should print nothing (migrations/coverage excluded)
grep -rn "on_delete=models.CASCADE\|on_delete=models.SET_NULL\|on_delete=models.SET_DEFAULT" apps --include=*.py \
  | grep -v "/migrations/" || echo "OK — no non-PROTECT on_delete in model code"
```

See also:

- [`docs/guides/README.md`](README.md) — guide index
- [`apps/app_base/models.py`](../../apps/app_base/models.py) — `BaseModel` /
  soft delete
- [`apps/app_base/managers.py`](../../apps/app_base/managers.py) — managers &
  soft-delete queryset
