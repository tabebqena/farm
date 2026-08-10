# Refactor: Hide Item-Correction Types from Admin Filter

## Problem

[`AdjustmentType`](apps/app_adjustment/models.py:26) contains 4 types (`PURCHASE_ITEM_CORRECTION_INCREASE`, `PURCHASE_ITEM_CORRECTION_DECREASE`, `SALE_ITEM_CORRECTION_INCREASE`, `SALE_ITEM_CORRECTION_DECREASE`) that are only used internally by [`InvoiceItemAdjustment.finalize()`](apps/app_adjustment/models.py:441). They should not be visible to users creating financial adjustments.

The [`AccountingAdjustmentForm`](apps/app_adjustment/forms.py:48-85) already hardcodes its own type lists excluding these — so the manual adjustment form is clean. But the Django admin's [`list_filter = ["type"]`](apps/app_adjustment/admin.py:9) shows **all** `AdjustmentType` values including the internal ones.

## Solution

Keep the 4 types in `AdjustmentType` as valid data values. Only change is in the admin: replace the simple `list_filter` with a custom `SimpleListFilter` subclass that excludes item-correction types from the dropdown.

### Files to modify

| File | Change |
|------|--------|
| [`admin.py`](apps/app_adjustment/admin.py) | Add `FinancialAdjustmentTypeFilter` class + update `list_filter` |

### What stays the same

- `AdjustmentType` enum — unchanged
- `Adjustment.type` field — unchanged  
- `Adjustment.clean()` — still validates `is_general()` etc.
- `InvoiceItemAdjustment.finalize()` — still uses `AdjustmentType.*_ITEM_CORRECTION_*`
- `AccountingAdjustmentForm` — already correct
- `AdjustableMixin.effective_amount` — still iterates all `AdjustmentType` values

### Implementation

Create a custom admin filter:

```python
class FinancialAdjustmentTypeFilter(admin.SimpleListFilter):
    title = _("type")
    parameter_name = "type"

    def lookups(self, request, model_admin):
        return [
            (t.value, t.label)
            for t in AdjustmentType
            if not AdjustmentType.is_item_correction(t)
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(type=self.value())
        return queryset
```

Then update `AdjustmentAdmin`:
```python
list_filter = [FinancialAdjustmentTypeFilter]
```
