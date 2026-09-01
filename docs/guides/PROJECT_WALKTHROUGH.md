# Farm Project Walkthrough & Debug Logging Guide

## Quick Start: Enable Debug Logging

The project uses standard Python logging. To see debug messages, temporarily set
the `farm` logger to `DEBUG` in `farm/settings.py`:

```bash
# Run development server with logging output
python manage.py runserver
```

All application logging uses the shared `farm` logger
(`from apps.app_base.logging_utils import logger`) plus a compliance-only
`farm_audit` logger (`logs/audit.log`). See
[../logging/LOGGING_STANDARDS.md](../logging/LOGGING_STANDARDS.md).

## Architecture Overview

```
Farm = Financial Management System for Livestock Farm

┌─────────────────────────────────────────────────────────┐
│                    OPERATIONS (14 types)                 │
│  Purchase, Sale, Expense, Birth, Death, Consumption,    │
│  Advance, Capital Gain/Loss, Internal Transfer, etc.    │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   ┌─────────┐  ┌─────────┐  ┌──────────────┐
   │ Entity  │  │Inventory│  │ Adjustments  │
   │ (Funds) │  │ (Assets)│  │ (Corrections)│
   └─────────┘  └─────────┘  └──────────────┘
        │              │              │
        └──────────────┼──────────────┘
                       │
                       ▼
          ┌──────────────────────┐
          │ Transactions/Ledger  │
          │ (Fund movements)     │
          └──────────────────────┘
```

## Core Concepts

### 1. **Operations** (`app_operation`)
- **What**: Business events (purchase, sale, expense, birth, death, etc.)
- **14 Types**: Each with specific source/destination rules
- **Key File**: `apps/app_operation/models/operation.py`
- **Debug Points**: `Operation.save()` logs all operation creates/updates

**Example Flow**:
```
User creates Purchase → Operation record created → Invoice items added 
→ Products linked → Transactions issued → Fund balances updated
```

### 2. **Entities** (`app_entity`)
- **What**: Business actors (projects, vendors, workers, clients, etc.)
- **Structure**: Entity types with Fund wallets for each operation
- **Key File**: `apps/app_entity/models.py`

### 3. **Inventory** (`app_inventory`)
- **What**: Products and ledger entries tracking asset movements
- **Key File**: `apps/app_inventory/models.py`
- **Debug Points**: Product creation, ledger entry recording

### 4. **Transactions** (`app_transaction`)
- **What**: Fund ledger entries recording money flows
- **Key File**: `apps/app_transaction/models.py`
- **Linked to**: Operations (issuance and payment transactions)

### 5. **Adjustments** (`app_adjustment`)
- **What**: Corrections to purchases, sales, and expenses
- **2 Types**:
  - **Adjustment**: Simple fund adjustments (return, discount, etc.)
  - **InvoiceItemAdjustment**: Line-level corrections with automatic Adjustment creation
- **Key File**: `apps/app_adjustment/models.py`
- **Debug Points**: 
  - `Adjustment.clean()` - validates adjustment types
  - `InvoiceItemAdjustment.finalize()` - computes net delta and creates Adjustment
  - `InvoiceItemAdjustmentLine.save()` - syncs ProductLedgerEntry

## Debug Logging Deep Dive

### Debug Module Location
**File**: `apps/app_base/logging_utils.py`

### Standard Logging

Logging is standard Python `logging` with a single shared logger and a
compliance-only audit channel:

```python
from apps.app_base.logging_utils import logger, audit_logger

logger.debug("Detail trace")              # silent unless farm logger is DEBUG
logger.info("Significant event")
logger.warning("Suspicious condition")
logger.error("Failure")

audit_logger.info("entity_created | Entity:1 | user=officer")
```

There are no custom decorators or context managers — log the meaningful steps
explicitly. `logger.debug(...)` calls are silent by default (the `farm` logger
is `INFO`); raise it to `DEBUG` in `farm/settings.py` to trace.

### Debug Points Across the Project

#### **Purchase Wizard** (`apps/app_operation/views/purchase_wizard.py`)
- **Step 1**: Basic info validation → Session storage
- **Step 2**: Invoice items → **Operation creation** (heavily logged)
- **Step 3**: Optional payment recording
- **Step 4**: Optional goods receipt (inventory movement)

**Key Logs**:
```
🌐 purchase_wizard_view [step=1/2/3/4]
  ⚡ Project loaded
  ⚡ Vendor count check
  → Creating purchase operation and invoice items
    ⚡ Creating PurchaseOperation record
    ✓ Operation created (pk=123)
    ⚡ Saving invoice items
    ✓ Saved 5 invoice items
    ⚡ Creating Product instances
    ✓ Product instances created
  ← Creating purchase (0.245s)
```

#### **Operation Model** (`apps/app_operation/models/operation.py`)
All operation saves are logged with context:

```python
def save(self, *args, **kwargs):
    result = super().save(*args, **kwargs)
    logger.debug(f"Operation saved | pk={self.pk} | type={self.operation_type}")
    action = "operation_created" if is_new else "operation_updated"
    audit_logger.info(f"{action} | Operation:{self.pk} | user={self.officer} | ...")
    return result
```

#### **Adjustments** (`apps/app_adjustment/models.py`)

**Adjustment.clean()**:
```
⚡ Adjustment.clean() for operation 456 | {"type": "PUR_RET", "amount": 500.00}
✓ Adjustment validation passed
```

**InvoiceItemAdjustment.finalize()**:
```
→ InvoiceItemAdjustment.finalize() | {"item_adjustment_pk": 789, "type": "PURCHASE_ITEM_INCREASE"}
  ⚡ Computing net delta from 3 lines | {"line_count": 3}
  ⚡ Net delta computed | {"total_delta": 250.50, "is_increase": true}
  ⚡ Adjustment type mapped | {"input_type": "PURCHASE_ITEM_INCREASE", "output_type": "PURCHASE_ITEM_CORRECTION_INCREASE"}
  → Creating Adjustment record | {"type": "PURCHASE_ITEM_CORRECTION_INCREASE", "amount": 250.50}
    ⚡ Adjustment validation passed
    ✓ Adjustment saved (pk=999)
  ← Creating Adjustment (0.045s)
  ✓ InvoiceItemAdjustment finalized
← InvoiceItemAdjustment.finalize() (0.156s)
```

**InvoiceItemAdjustmentLine.save()**:
```
⚡ InvoiceItemAdjustmentLine.save() | {"pk": 1001, "is_removed": false, "quantity_delta": 5.00, "value_delta": 250.50}
  ⚡ Recording ProductLedgerEntry for adjustment line
  ✓ ProductLedgerEntry recorded (pk=1001)
```

#### **Signals** (`apps/app_operation/signals.py`)
Auto-logged with decorator:

```
📡 create_initial_period (Entity) | {"signal": "create_initial_period", "sender": "Entity"}
  ⚡ Evaluating create_initial_period | {"instance_pk": 1, "created": true}
  → Creating initial FinancialPeriod | {"entity_pk": 1, "start_date": "2026-04-22"}
    ✓ Initial FinancialPeriod created
  ← Creating initial FinancialPeriod (0.032s)
📡 Signal handler completed
```

## Common Debugging Workflows

### 1. **Trace a Purchase Creation**
```bash
# Set DEBUG=True in Django settings
python manage.py runserver

# Then in browser: POST /purchase/1/step/2/
# Watch the console output for full trace:
# - Project loading
# - Vendor validation
# - Formset processing
# - Operation creation
# - Invoice items saving
# - Product creation
# - Session cleanup
```

### 2. **Debug an Adjustment Finalization Error**
```python
# In shell
from apps.app_adjustment.models import InvoiceItemAdjustment

adj = InvoiceItemAdjustment.objects.get(pk=123)
adj.finalize()

# See detailed logs showing:
# - Line deltas computed
# - Type mapping logic
# - Adjustment creation and validation
# - Ledger entries created
```

### 3. **Monitor Transaction Creation**
The `Operation.save()` logs show when transactions are issued:
```
→ Operation.save() (PURCHASE)
  ⚡ Validating 3 invoice items
  ✓ Operation saved
  ← Transactions auto-created via LinkedIssuanceTransactionMixin
← Operation.save() (0.085s)
```

### 4. **Track Inventory Movements**
ProductLedgerEntry recording is logged in:
- `InvoiceItemAdjustmentLine.save()`
- `Operation.save_inventory()`
- Adjustment reversals

## Files Modified with Debug Logging

1. **`apps/app_base/debug.py`** (NEW)
   - Central debug utilities and decorators

2. **`apps/app_operation/models/operation.py`**
   - `Operation.save()` - Full context logging

3. **`apps/app_operation/views/purchase_wizard.py`**
   - `purchase_wizard_view()` - All steps traced
   - `_handle_step_2_post()` - Operation creation detailed
   - All helper functions with context

4. **`apps/app_adjustment/models.py`**
   - `Adjustment.clean()` - Validation logging
   - `InvoiceItemAdjustment.finalize()` - Net delta computation
   - `InvoiceItemAdjustmentLine.save()` - Ledger entry recording
   - `InvoiceItemAdjustment.reverse()` - Reversal process

5. **`apps/app_operation/signals.py`**
   - `create_initial_period()` - Signal handler logging
   - `register()` - Signal registration status

## Performance Notes

**Debug Logging Overhead**: 
- Context manager timing: ~0.1-0.5ms per section
- Function decorator: ~0.05-0.2ms per call
- Safe to keep enabled in development/staging

**In Production**:
- Set logging level to `WARNING` to disable debug messages
- No performance impact when not reading logs

## Log Level Configuration

In `farm/settings.py` or `settings/development.py`:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'farm': {
            'handlers': ['console', 'debug_file'],
            'level': 'INFO',  # Change to 'DEBUG' to trace, 'WARNING' in production
            'propagate': False,
        },
    },
}
```

## Key Metrics Tracked

The debug logging captures:
- **Count metrics**: Item counts, line counts, form counts
- **Amount metrics**: Total amounts, deltas, adjustments
- **State transitions**: Is_new, created_at, updated_at
- **Relationships**: FK references (pk values)
- **Timestamps**: Dates, times, elapsed duration
- **User context**: Officer, operator, request user

## Troubleshooting Common Issues

### Issue: "Session expired" in Purchase Wizard
**Debug output to check**:
```
⚡ Step 2 POST handler started
❌ Session expired in step 2 | {"session_key": "purchase_wizard_1"}
```
→ Session was cleared between step 1 and step 2

### Issue: Operation creation fails
**Debug output to check**:
```
→ Creating purchase operation and invoice items
  ❌ Exception creating operation and items
```
→ Check the exception details in the next log line for the cause

### Issue: Adjustment finalization error
**Debug output to check**:
```
→ InvoiceItemAdjustment.finalize()
  ⚡ Computing net delta from 0 lines
  ❌ Net adjustment is zero
```
→ No adjustment lines were created before calling finalize()

## Next Steps

1. **Enable debug logging** in your Django settings
2. **Run the purchase wizard** through all steps and watch the console
3. **Create adjustments** and monitor finalization
4. **Check transaction creation** through operation saves
5. **Trace reversal operations** to see the full reversal chain

The comprehensive logging makes it easy to:
- Understand the flow of complex operations
- Identify exactly where errors occur
- Performance-profile critical paths
- Train team members on the system
- Debug production issues safely
