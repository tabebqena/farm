# Analysis: Can `create_from_session` use `save_inventory`?

## Current Architecture

### Two Creation Paths for Purchase Operations

```
Path A (Standard Create View)           Path B (Wizard create_from_session)
  ──────────────────────────              ───────────────────────────────
  1. _create_operation()                  1. Integrity check
     → saves Operation                    2. Create + save Operation
  2. _process_invoice()                   3. Create InvoiceItems
     → build formset                      4. Create InventoryMovementLines
     → formset.save()                           (for received quantities)
     → op.save_inventory(formset)         5. ProductLedgerEntry.record(op)
         → ProductLedgerEntry.record()    6. Payment transaction (if paid > 0)
  3. _process_payment()
```

### What `save_inventory` does for **PURCHASE**

```python
def save_inventory(self, bound_formset):
    product_map = {}

    # Step 1: Auto-create movements (PURCHASE NOT in this list)
    if self.operation_type in (BIRTH, DEATH):
        self._auto_create_inventory_movements(bound_formset)
        # ← PURCHASE is skipped here

    # Step 2: Build product_map (PURCHASE NOT in this list)
    if self.operation_type in (DEATH, CONSUMPTION, CAPITAL_GAIN, CAPITAL_LOSS):
        # ← PURCHASE is skipped here

    # Step 3: Write issuance entries — for ALL operation types
    ProductLedgerEntry.record(self, product_map=product_map or None)
    # ← For PURCHASE, this is the ONLY thing that runs
```

**For PURCHASE operations, `save_inventory` is effectively just:**
```python
ProductLedgerEntry.record(self)
```

### What `create_from_session` does

```python
# Step 4: Create InventoryMovementLines (if received_qty > 0)
InventoryMovementLine.objects.create(
    operation=op, invoice_item=invoice_item,
    product=None,  # ← lazy-created by InventoryMovementLine.save()
    quantity=received_qty, date=date_val, ...
)

# Step 5: Record issuance entries
ProductLedgerEntry.record(op)  # ← Same call as save_inventory's step 3
```

---

## Key Differences

| Aspect | Standard Create View | Wizard `create_from_session` |
|--------|---------------------|------------------------------|
| **Data source** | HTTP POST → bound formset | Wizard session dict |
| **Movement lines** | Created later by user (UI-driven) | Created eagerly for `received_qty > 0` |
| **Lazy product creation** | Via `InventoryMovementLine.save()` when user creates movement | Same mechanism in `create_from_session` |
| **Issuance entries** | Via `save_inventory → ProductLedgerEntry.record()` | Direct `ProductLedgerEntry.record(op)` |
| **Payment** | Separate `_process_payment` step | Inline after issuance |

---

## Can `create_from_session` call `save_inventory`?

**Directly?** No — `save_inventory` requires a `bound_formset` parameter. It expects Django form objects with `cleaned_data` containing fields like `selected_product`. Passing raw dict data would fail.

**Indirectly via refactoring?** Possibly, but with trade-offs:

### Option 1: Make `save_inventory` accept session data

Add an alternative data source (dict instead of formset):

```python
def save_inventory(self, bound_formset=None, session_data=None):
    # ... 
```

**Pros:**
- Unified issuance logic in one place
- Any future changes to issuance logic apply to both paths

**Cons:**
- Increased method complexity (two code paths)
- Must still build InvoiceItems + movement lines outside this method
- Won't eliminate movement line creation (still duplicated)

### Option 2: Split `save_inventory` — extract issuance into a separate method

```python
def _record_issuance(self, product_map=None):
    ProductLedgerEntry.record(self, product_map=product_map)
```

Both paths call `_record_issuance()` instead of duplicating `ProductLedgerEntry.record()`.

**Pros:**
- Clean separation — movement logic stays where it belongs
- Both paths share issuance logic
- Minimal change

**Cons:**
- Minor refactoring — not a major win

### Option 3: Refactor wizard to use the standard create flow

Make the wizard build a fake request.POST and use the standard `_process_invoice` path.

**Pros:**
- Complete unification of both paths
- All inventory logic in one place

**Cons:**
- Major refactoring — high risk
- Fighting Django's form machinery from wizard session data
- The wizard eagerly creates movement lines, which is **intentional design**, not an accident
- Would force the wizard to match the standard view's lifecycle

---

## Verdict: Is it worth it?

### Current State Assessment

`create_from_session` already calls `ProductLedgerEntry.record(op)` (line 201), which is **exactly** what `save_inventory` does for PURCHASE operations. The duplication is minimal — just one line.

The real duplication issue is not `save_inventory` vs `ProductLedgerEntry.record()` but rather the **movement line creation logic**:

- **Wizard**: Creates movement lines eagerly for `received_qty > 0` during `create_from_session`
- **Standard view**: Movement lines are user-created later via a dedicated UI

These are **intentionally different behaviors** for different user experiences. The wizard is a streamlined bulk-creation flow; the standard view is a step-by-step process.

### Recommendation

**Do NOT refactor `create_from_session` to use `save_inventory`.** The coupling to Django formsets makes it architecturally incompatible. However, consider this minor improvement:

### Minor Refactoring Option

Extract the issuance recording into a thin wrapper method on [`Operation`](apps/app_operation/models/operation.py:538) to make the intent clearer:

```python
# On Operation base class
def record_issuance(self, product_map=None):
    """Write issuance ledger entries for this operation."""
    ProductLedgerEntry.record(self, product_map=product_map)
```

Then:
- `save_inventory()` would call `self.record_issuance(product_map)`
- `create_from_session()` would call `self.record_issuance()` (replacing the current direct `ProductLedgerEntry.record(op)`)

This gives you:
✅ Shared issuance logic
✅ Cleaner intent
✅ Minimal change footprint
✅ No formset coupling

---

## Summary Pros/Cons Table

| Approach | Pros | Cons |
|----------|------|------|
| **Use `save_inventory` directly** | ❌ Not possible — formset coupling | |
| **Refactor `save_inventory` for dual input** | ✅ Unified issuance logic | ❌ Increased complexity; movement duplication remains |
| **Split out issuance method** | ✅ Minimal change; cleaner code | ❌ Minor refactoring; limited benefit |
| **Refactor wizard to standard flow** | ✅ Full unification | ❌ High risk; breaks wizard design intent |
| **Leave as-is** | ✅ Both paths work correctly today | ❌ Slight duplication (`ProductLedgerEntry.record` is called from two places) |
