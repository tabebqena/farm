# Fix: Adjustment Card Wrongly Marks the Adjustment Effect Indicator

## Bug Analysis

### Root Cause
In both [`operation_detail.html`](apps/app_operation/templates/app_operation/operation_detail.html:44) and [`adjustments_list.html`](apps/app_operation/templates/app_operation/adjustments_list.html:75), the template uses `{% if adj.amount < 0 %}` to determine whether an adjustment is a **decrease** (shown as `text-danger` red) or an **increase** (shown as `text-success` green).

However, the `amount` field on the `Adjustment` model is **always stored as a positive value**:
- The form [`AccountingAdjustmentForm`](apps/app_adjustment/forms.py:21) defines `min_value=Decimal("0.01")`
- The [`InvoiceItemAdjustment.finalize()`](apps/app_adjustment/models.py:545) method uses `abs(total_delta)`

Since `adj.amount` is always positive, `adj.amount < 0` evaluates to `False` for **every** adjustment, causing **all** adjustments to display as `text-success` (green) with a `+` prefix — even reductions (returns, discounts, shortages, etc.) which should show as decreases.

### Direction is Type-Based, Not Amount-Based
The direction (increase vs decrease) is encoded in the [`AdjustmentType`](apps/app_adjustment/models.py:25) field via the [`is_reduction()`](apps/app_adjustment/models.py:125) classmethod:
- **Reduction types** (`is_reduction()` returns `True`): returns, discounts, overcharges, shortages, damage allowances, write-offs, general reductions, item correction decreases — these **decrease** the operation's total
- **Increase types** (`is_reduction()` returns `False`): undercharges, tax additions, freight, late fees, general increases, item correction increases — these **increase** the operation's total

## Fix Plan

### Step 1: Add `is_reduction` property to `Adjustment` model
**File:** [`apps/app_adjustment/models.py`](apps/app_adjustment/models.py:159)

Add an instance property that wraps the classmethod:
```python
@property
def is_reduction(self):
    return AdjustmentType.is_reduction(self.type)
```

This makes `adj.is_reduction` accessible in Django templates.

### Step 2: Fix `operation_detail.html`
**File:** [`apps/app_operation/templates/app_operation/operation_detail.html`](apps/app_operation/templates/app_operation/operation_detail.html:44)

Replace:
```django
<span class="fw-bold {% if adj.amount < 0 %}
    ...many blank lines...
    text-danger
    ...many blank lines...
  {% else %}
    ...many blank lines...
    text-success
    ...many blank lines...
  {% endif %}">
  {% if adj.amount < 0 %}
    {{ currency }}{{ adj.amount }}
  {% else %}
    +{{ currency }}{{ adj.amount }}
  {% endif %}
</span>
```

With:
```django
<span class="fw-bold {% if adj.is_reduction %}text-danger{% else %}text-success{% endif %}">
  {% if adj.is_reduction %}
    -{{ currency }}{{ adj.amount }}
  {% else %}
    +{{ currency }}{{ adj.amount }}
  {% endif %}
</span>
```

Key changes:
- `adj.amount < 0` → `adj.is_reduction`
- Reduction amounts show with `-` prefix (as `- $X.XX`) instead of just `$X.XX`
- Clean up the excessive whitespace/blank lines

### Step 3: Fix `adjustments_list.html`
**File:** [`apps/app_operation/templates/app_operation/adjustments_list.html`](apps/app_operation/templates/app_operation/adjustments_list.html:75)

Same changes as Step 2.

### Step 4: Verify no other templates have the same bug
Search across templates for `adj.amount < 0` or similar patterns to ensure no other locations need fixing.

## Visual Impact

| Adjustment Type | Before | After |
|---|---|---|
| Purchase Return (reduction) | `+$100.00` (green) | `-$100.00` (red) |
| Purchase Discount (reduction) | `+$50.00` (green) | `-$50.00` (red) |
| Purchase Undercharge (increase) | `+$200.00` (green) | `+$200.00` (green) |
| Sale Return (reduction) | `+$75.00` (green) | `-$75.00` (red) |
| Sale Late Fee (increase) | `+$25.00` (green) | `+$25.00` (green) |
