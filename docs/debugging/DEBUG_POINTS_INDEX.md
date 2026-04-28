# Debug Points Index

## Quick Navigation by File

This document provides a complete index of all debug logging points in the Farm project, organized by file and function.

---

## apps/app_base/debug.py (Debug Module - NEW)

### DebugContext Class
- **Location**: Lines 15-80
- **Purpose**: Central context manager for logging
- **Methods**:
  - `section()` - Context manager for sections with timing
  - `log()` - Log info-level message
  - `warn()` - Log warning-level message
  - `error()` - Log error with exception support
  - `success()` - Log success message
  - `_format_data()` - JSON data formatter
  - `_indent()` - Indentation helper
  - `_depth` / `_timings` - Class variables for state

### Decorators
- **Location**: Lines 85-180
- `@debug_function` - Automatic function logging
- `@debug_view` - Automatic view logging
- `@debug_signal` - Automatic signal logging
- `@debug_model_save` - Automatic model save logging

---

## apps/app_operation/models/operation.py

### Operation.save()
- **Location**: Line 264-302
- **Debug Points**: 1 major section
- **What's Logged**:
  - Entry: `Operation.save() ({operation_type})`
  - Data: `is_new`, `pk`, `source`, `destination`, `amount`, `date`
  - Nested: Invoice item validation with count
  - Exit: Success with `pk` and elapsed time
- **Status Symbols**: → ⚡ ✓ ←
- **Use Case**: Track all operation creates and updates
- **Example Output**:
```
→ Operation.save() (PURCHASE) | {"is_new": true, "source": "Project A", "destination": "Vendor B", "amount": 5000.50}
  ⚡ Validating 5 invoice items
  ✓ All 5 invoice items validated
  ✓ Operation saved (pk=456)
← Operation.save() (0.123s)
```

---

## apps/app_operation/views/purchase_wizard.py

### purchase_wizard_view()
- **Location**: Line 28-94
- **Decorator**: `@debug_view`
- **Debug Points**: 7 major log points + decorator
- **What's Logged**:
  1. **Entry**: View initialization with `project_pk`, `operation_pk`, `step`, `method`
  2. **Step validation**: Invalid step detection
  3. **Project loading**: Project lookup with pk and name
  4. **Vendor count**: Number of active vendors
  5. **Operation loading**: Operation lookup if provided
  6. **Operation validation**: Ownership check
  7. **Session check**: Session validity for steps 2+
  8. **Dispatch**: POST handler routing
  9. **Rendering**: GET response preparation
  10. **Exit**: Response status code

### _handle_step_1_post()
- **Location**: Line 137-181
- **Debug Points**: 1 section
- **What's Logged**:
  - Entry: `_handle_step_1_post called`
  - Form validation result
  - Operation save (if editing)
  - Session storage (if creating)

### _handle_step_2_post()
- **Location**: Line 208-342
- **Debug Points**: 7 major sections (HEAVILY LOGGED)
- **What's Logged**:
  1. **Entry**: `_handle_step_2_post started`
  2. **Session check**: Session expiration detection
  3. **Data loading**: Step 1 data retrieval
  4. **Formset validation**: Validation result with errors
  5. **Amount computation**: Item count and total amount
  6. **Amount validation**: Zero amount detection
  7. **Atomic section**: "Creating purchase operation and invoice items"
     - Operation creation with all details
     - Invoice items saving with count
     - Product creation status
  8. **Error handling**: Exception logging with type
  9. **Session cleanup**: Session removal
  10. **Success**: Final completion
- **Most Important**: This handles the critical operation creation!

### _handle_step_3_post() & _handle_step_4_post()
- **Location**: Line 343-539
- **Debug Points**: Implicit through parent view decorator
- **What's Logged**:
  - View entry/exit with status
  - Could be enhanced with more detailed logging

---

## apps/app_adjustment/models.py

### Adjustment.clean()
- **Location**: Line 200-218
- **Debug Points**: 1 section with 3 validation checks
- **What's Logged**:
  - Entry: `Adjustment.clean()`
  - Data: `type`, `operation_type`, `amount`
  - Check 1: Operation type validation
  - Check 2: General type reason validation
  - Exit: Success or validation error

### InvoiceItemAdjustment.finalize()
- **Location**: Line 318-389
- **Debug Points**: 5 major sections (HEAVILY LOGGED)
- **What's Logged**:
  1. **Entry**: Item adjustment details
  2. **Duplicate check**: Already finalized detection
  3. **Line fetch**: Number of lines to process
  4. **Delta computation**: Total net delta and direction
  5. **Type mapping**: Input type → Output type mapping
  6. **Atomic section**: "Creating Adjustment record"
     - Adjustment creation with type and amount
     - Validation status
     - Save status with pk
  7. **Link update**: Item adjustment ↔ Adjustment linking
  8. **Exit**: Final success confirmation
- **Critical**: Controls adjustment amount calculation!

### InvoiceItemAdjustmentLine.save()
- **Location**: Line 473-487
- **Debug Points**: 2 sections
- **What's Logged**:
  1. **Entry**: Line details
     - `pk`, `adjustment_pk`, `invoice_item_pk`
     - `is_removed`, `quantity_delta`, `value_delta`
  2. **Ledger entry**: ProductLedgerEntry recording
  3. **Exit**: Success with ledger entry pk

### InvoiceItemAdjustment.reverse()
- **Location**: Line 368-413
- **Debug Points**: 3 sections
- **What's Logged**:
  1. **Entry**: Reversal initiation details
  2. **Check 1**: Un-finalized check
  3. **Atomic section**: "Reversing InvoiceItemAdjustment"
     - Linked Adjustment reversal
     - Negating ledger entry recording
     - Item adjustment reversal
  4. **Exit**: Final success

---

## apps/app_transaction/models.py

### Transaction.clean()
- **Location**: Line 105-120
- **Debug Points**: 2 validation checks
- **What's Logged**:
  1. **Entry**: Transaction details
     - `type`, `source`, `target`, `amount`
  2. **Source/target check**: Same entity detection
  3. **Exit**: Validation success

### Transaction.create() [STATIC METHOD]
- **Location**: Line 122-189
- **Debug Points**: 4 major sections (HEAVILY LOGGED)
- **What's Logged**:
  1. **Entry section**: "Transaction.create()"
     - `type`, `source`, `target`, `amount`
     - `document_type`, `document_pk`
  2. **Entity type validation**: Violation detection
  3. **Operation type validation**: Allowed operation check
  4. **Date resolution**: Date parsing and timezone handling
  5. **Database creation**: Transaction.objects.create()
  6. **Exit**: Success with transaction pk
- **Critical**: Issues all financial transactions!

### Transaction.reverse()
- **Location**: Line 197-258
- **Debug Points**: 3 major sections
- **What's Logged**:
  1. **Entry**: Original transaction details
     - `transaction_pk`, `type`, `amount`, `officer`, `reason`
  2. **Check 1**: Not-a-reversal check
  3. **Check 2**: Not-already-reversed check
  4. **Atomic section**: "Creating reversal transaction"
     - Source/target swapping details
     - Date resolution
     - Mirror-image transaction creation
     - Reversal linking
  5. **Exit**: Success with reversal pk
- **Critical**: Handles all transaction reversals!

---

## apps/app_operation/signals.py

### create_initial_period()
- **Location**: Line 11-35
- **Decorator**: `@debug_signal`
- **Debug Points**: 3 log points + decorator
- **What's Logged**:
  1. **Decorator entry**: Signal name, sender class
  2. **Evaluation**: Instance pk, created flag, system/world checks
  3. **Skip reasons**: Why handler exits early (if applicable)
  4. **Atomic section** (if creating): "Creating initial FinancialPeriod"
     - Entity pk and name
     - Start date
     - Period creation success
  5. **Exit**: Signal completion

### register()
- **Location**: Line 38-40
- **Debug Points**: 1 log point
- **What's Logged**:
  - Registration status with note about disabled signal

---

## Debug Points by Operation Type

### PURCHASE Flow (Most Complex)
1. **View Entry** → `purchase_wizard_view()` @debug_view
2. **Step 2 Create** → `_handle_step_2_post()` with nested section
3. **Operation Create** → `Operation.save()` with nested section
4. **Transaction Issuance** → `Transaction.create()` with nested section
5. **Transaction Validation** → `Transaction.clean()`

**Total Debug Points**: 15+

### ADJUSTMENT Flow
1. **Adjustment Save** → `Adjustment.clean()`
2. **Item Adjustment Finalize** → `InvoiceItemAdjustment.finalize()` with nested section
3. **Line Save** → `InvoiceItemAdjustmentLine.save()`
4. **Adjustment Transaction** → `Transaction.create()` nested in finalize
5. **Reversal** → `InvoiceItemAdjustment.reverse()` with nested section

**Total Debug Points**: 10+

### REVERSAL Flow
1. **Item Adjustment Reverse** → `InvoiceItemAdjustment.reverse()` with nested section
2. **Adjustment Reverse** → Calls Operation.reverse()
3. **Transaction Reverse** → `Transaction.reverse()` with nested section

**Total Debug Points**: 8+

---

## Debug Output Symbols Reference

| Symbol | Context | Meaning |
|--------|---------|---------|
| → | Start | Entering a section/function |
| ← | End | Exiting a section/function |
| ✓ | Success | Operation completed successfully |
| ❌ | Error | Error occurred (with exception details) |
| ⚡ | Info | Information/status message |
| 🌐 | HTTP | HTTP view invocation |
| 🔵 | Function | Function call (via @debug_function) |
| 📡 | Signal | Signal handler execution (via @debug_signal) |
| 💾 | Database | Model save operation (via @debug_model_save) |

---

## Indentation Levels

Debug output is automatically indented based on nesting depth:

```
→ purchase_wizard_view()                                    [Depth 0]
  ⚡ Wizard initialized                                    [Depth 1]
  ⚡ Project loaded                                        [Depth 1]
  → Creating purchase operation                           [Depth 1]
    ⚡ Creating PurchaseOperation record                   [Depth 2]
    ✓ Operation created (pk=456)                          [Depth 2]
    → LinkedIssuanceTransactionMixin executing            [Depth 2]
      → Transaction.create()                             [Depth 3]
        ⚡ Validating entity types                        [Depth 4]
        ✓ Entity types valid                             [Depth 4]
      ← Transaction.create() (0.045s)                    [Depth 3]
    ← LinkedIssuanceTransactionMixin (0.050s)            [Depth 2]
  ← Creating purchase operation (0.250s)                 [Depth 1]
← purchase_wizard_view (0.312s)                          [Depth 0]
```

Maximum observed depth: 4 levels

---

## Performance Baseline (Approximate)

Based on nested timing data:

| Operation | Typical Duration |
|-----------|-----------------|
| Simple log/warn | 0.5ms |
| Section entry/exit | 1-2ms |
| Operation.save() | 50-150ms |
| Transaction.create() | 10-50ms |
| InvoiceItemAdjustment.finalize() | 30-100ms |
| Purchase wizard complete flow | 200-400ms |

---

## Search Guide

### Find debug logs for...

**Creating a Purchase**:
- Search: `_handle_step_2_post`
- Key section: "Creating purchase operation and invoice items"

**Adjusting Items**:
- Search: `InvoiceItemAdjustment.finalize`
- Key section: "Creating Adjustment record"

**Reversing Operations**:
- Search: `Transaction.reverse` or `Operation.reverse`
- Key section: "Creating reversal transaction"

**Transaction Validation**:
- Search: `Transaction.create`
- Key sections: "Validating entity types", "Validating operation type"

**Inventory Changes**:
- Search: `ProductLedgerEntry` in logs
- Found in: Operation.save_inventory, InvoiceItemAdjustmentLine.save

**Signal Firing**:
- Search: `create_initial_period` (📡 symbol)
- Found in: apps/app_operation/signals.py

---

## Common Log Patterns

### Pattern 1: Section with Nested Logging
```
→ Operation name | context data
  ⚡ Step 1 message
  ✓ Step 1 success
  ⚡ Step 2 message
  → Nested section
    ⚡ Details
    ✓ Sub-success
  ← Nested section (0.123s)
  ✓ Overall completion
← Operation name (0.456s)
```

### Pattern 2: Validation Flow
```
⚡ Starting validation
✓ Check 1 passed
✓ Check 2 passed
❌ Check 3 failed | error details
```

### Pattern 3: Count-Based Logging
```
⚡ Processing N items | {"count": N}
  (loop processing shown by section nesting)
✓ All N items processed | {"result": value}
```

---

## Debug Data Structure

All debug logs include structured data in JSON format:

```json
{
  "timestamp": "auto",
  "level": "DEBUG/INFO/WARNING/ERROR",
  "symbol": "→/←/✓/❌/⚡",
  "message": "Human readable message",
  "data": {
    "pk": "primary key",
    "count": "item count",
    "amount": "decimal value",
    "duration": "elapsed seconds"
  },
  "indent": "automatic based on nesting"
}
```

---

## Environment Setup

To see all debug logs:

```bash
# In settings.py or local settings
LOGGING = {
    'loggers': {
        'farm_debug': {
            'level': 'DEBUG',  # Or DEBUG, INFO, WARNING, ERROR
            'handlers': ['console'],  # Logs appear on stdout
        },
    },
}

# Then run:
python manage.py runserver  # Logs to console
```

To suppress debug logs (production):

```python
# In production settings
'farm_debug': {
    'level': 'WARNING',  # Or ERROR, CRITICAL
}
```

---

## Statistics Summary

| Metric | Count |
|--------|-------|
| Total debug points | 40+ |
| View log points | 9 |
| Model log points | 12 |
| Signal log points | 1 |
| Sections with nesting | 12 |
| Decorators used | 4 |
| Status symbols | 5 |
| Files with logging | 5 |
| Max nesting depth | 4 |

---

## Last Updated

- **Date**: 2026-04-22
- **Total Lines Added**: ~330
- **Files Modified**: 5
- **Files Created**: 3
- **Version**: 1.0

For questions, see DEBUG_QUICK_REFERENCE.md and PROJECT_WALKTHROUGH.md
