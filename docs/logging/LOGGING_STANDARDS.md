# Comprehensive Logging Standards - Farm Project

## Overview

This project implements **extensive, multi-layer logging** for complete audit trails, debugging, and compliance. The existing `apps.app_base.debug` module has been **enhanced** with persistent file storage, transaction tracking, and QuerySet operation logging.

---

## Architecture

### 1. **Core Debug Module** (`apps.app_base.debug`)
- ✅ **DebugContext** — Structured logging with context indentation, timing, and nesting
- ✅ **Decorators** — @debug_function, @debug_model_save, @debug_view, @debug_signal
- ✅ **NEW: Audit Methods** — audit(), transaction_start(), transaction_commit(), transaction_rollback()
- ✅ **NEW: Transaction Decorators** — @debug_transaction, @debug_db_operation
- ✅ **Persistent Logging** — Automatic file handler configuration with rotating logs

### 2. **Audit Middleware** (`farm.middlewares_audit.AuditTrailMiddleware`)
- Logs all HTTP requests/responses with metadata
- Tracks request timing, status codes, user information
- Captures exceptions during request processing
- Enables end-to-end request tracing

### 3. **QuerySet Logging** (`apps.app_base.queryset_logging`)
- **LoggingQuerySet** — Tracks all QuerySet operations (delete, update, bulk_create, bulk_update)
- **LoggingManager** — Drop-in replacement for Django's Manager
- Prevents silent bulk operations from escaping audit trails

### 4. **Logging Configuration** (`farm/settings.py`)
- **Three persistent log files**:
  - `logs/debug.log` — General application debug logs
  - `logs/audit.log` — Compliance and audit trail logs (JSON-formatted)
  - `logs/errors.log` — Error and exception logs only
- **Rotating handlers** — 10MB per file, auto-rotation with backups
- **Level configuration** — DEBUG for apps, INFO for audit, ERROR-only for errors

---

## How to Use

### A. Basic Logging in Views

```python
from apps.app_base.debug import DebugContext, debug_view

@debug_view
def my_view(request):
    """View is automatically logged with request metadata."""
    with DebugContext.section("Processing user data"):
        DebugContext.log("Extracting form data")
        # ... process ...
        DebugContext.success("Processing completed")
    return response
```

**Output:**
```
→ Processing user data
  ⚡ Extracting form data
  ✓ Processing completed
← Processing user data (0.123s)
```

### B. Logging Database Operations

```python
from apps.app_base.debug import DebugContext, debug_model_save

class MyModel(models.Model):
    @debug_model_save()
    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with DebugContext.section(f"Deleting {self.__class__.__name__}"):
            DebugContext.log("Running pre-delete hooks")
            result = super().delete(*args, **kwargs)
            DebugContext.success("Deletion completed", {"pk": self.pk})
            return result
```

### C. Logging Financial Transactions

```python
from apps.app_base.debug import DebugContext, debug_transaction

class Transaction(models.Model):
    @debug_transaction(transaction_type="financial")
    def reverse(self, officer, reason=""):
        """Transaction reversal with full audit trail."""
        # Implementation automatically logged with:
        # - transaction_start()
        # - transaction_commit() on success
        # - transaction_rollback() on failure
        # - audit() trail entry
        ...
```

### D. Audit Trail Entries

```python
from apps.app_base.debug import DebugContext

# Log a critical operation
DebugContext.audit(
    action="payment_processed",
    entity_type="Payment",
    entity_id=payment.pk,
    details={
        "amount": float(payment.amount),
        "source": str(payment.source),
    },
    user=request.user.username
)
```

**Audit Log Output (JSON):**
```json
{
    "action": "payment_processed",
    "entity_type": "Payment",
    "entity_id": 42,
    "timestamp": "2026-04-28T14:23:45.123456",
    "user": "john.doe",
    "details": {
        "amount": 1000.50,
        "source": "Bank Account"
    }
}
```

### E. Using LoggingQuerySet

```python
from apps.app_base.queryset_logging import LoggingManager

class MyModel(models.Model):
    objects = LoggingManager()  # Replaces the default manager

# All operations are now logged
MyModel.objects.filter(status="pending").delete()  # ⚠️ Logged as bulk_delete
MyModel.objects.bulk_update(instances, fields)     # ✓ Logged
```

---

## What Should Be Logged

### 🔴 **Critical (Always Log)**
- ✅ Financial transactions (create, reverse, adjust)
- ✅ User authentication events (login, logout, permission changes)
- ✅ Data deletions (all delete operations)
- ✅ Bulk updates/modifications
- ✅ Status transitions (e.g., "pending" → "approved")
- ✅ Exceptions and errors
- ✅ Report generation

### 🟡 **Important (Log in Critical Paths)**
- ✅ Entity creation (Person, Supplier, Product)
- ✅ Inventory adjustments
- ✅ Form validations (especially failures)
- ✅ API calls and responses
- ✅ Cache operations
- ✅ Workflow transitions

### 🟢 **Optional (Debug Only)**
- ℹ️ Individual field reads
- ℹ️ Template rendering
- ℹ️ Non-critical calculations
- ℹ️ Loop iterations

---

## Log Levels

| Level  | Usage | File | Example |
|--------|-------|------|---------|
| DEBUG  | Detailed execution flow | debug.log | "Processing payment #123..." |
| INFO   | Audit trail & significant events | audit.log | Transaction created, user logged in |
| WARNING | Suspicious but recoverable | debug.log, errors.log | Attempt to delete protected record |
| ERROR  | Failures requiring attention | errors.log | Payment processing failed |
| CRITICAL | System failures | errors.log | Database connection lost |

---

## Audit Trail Checklist

Use this checklist when implementing critical operations:

### ✓ Financial Operations
- [ ] Transaction created → `DebugContext.audit("transaction_created", ...)`
- [ ] Transaction reversed → `DebugContext.audit("transaction_reversed", ...)`
- [ ] Adjustment applied → `DebugContext.audit("adjustment_created", ...)`
- [ ] Amount changed → Log old value, new value, reason

### ✓ Entity Operations
- [ ] Entity created → Include entity type, owner
- [ ] Entity status changed → Log state transition
- [ ] Contact info modified → Log what changed
- [ ] Stakeholder added/removed → Log stakeholder role

### ✓ Inventory Operations
- [ ] Product received → Log quantity, source
- [ ] Product dispensed → Log quantity, recipient
- [ ] Inventory adjustment → Log old count, new count, reason
- [ ] Product marked as SOLD/DEAD → Prevent future operations

### ✓ Access Control
- [ ] User login/logout → Automatic via Django, verify in audit.log
- [ ] Permission change → Who changed what, why
- [ ] Admin action → Log all admin modifications

### ✓ Error Handling
- [ ] Validation failure → Log what failed, why
- [ ] Transaction rollback → Log reason, original attempt
- [ ] Constraint violation → Log the constraint, entities involved

---

## Viewing Logs

### Console Output (Real-time)
```bash
# During development, logs appear in console
python manage.py runserver
```

### Audit Trail (Production Review)
```bash
# Review all audit events
tail -f logs/audit.log

# Filter by action
grep "transaction_reversed" logs/audit.log

# Parse JSON entries
cat logs/audit.log | grep "transaction_created" | jq .
```

### Debug Log (Troubleshooting)
```bash
# Follow debug output with context
tail -f logs/debug.log

# Find slow operations
grep "← " logs/debug.log | grep "([0-9.]*s)" | sort -t'(' -k2 -nr
```

### Error Log (Alert on Failures)
```bash
# See only errors
tail -f logs/errors.log

# Count errors per type
grep "ERROR" logs/errors.log | cut -d'|' -f3 | sort | uniq -c
```

---

## Example: Complete Financial Flow

```python
# 1. View logs the HTTP request (middleware)
# [AUDIT] request_start | POST /operations/create | user: john.doe

# 2. View handler logs execution
# → create_operation | {"type": "SALE", "product": "Rice", "qty": 100}

# 3. Model.create() logs financial transaction
# → Transaction.create() | {"type": "SALE", "amount": 5000.00}
# 💾 Transaction.save (create) | {"pk": 42}
# ✓ Transaction created | {"transaction_pk": 42}

# 4. Audit trail captures the event
# {"action": "transaction_created", "entity_type": "Transaction", "entity_id": 42, ...}

# 5. Signal handlers log any cascading actions
# 📡 post_save (Transaction)

# 6. View returns response
# [AUDIT] request_complete | 200 OK | elapsed: 245ms
```

---

## Extending Logging

### Add Logging to Existing Models

```python
from apps.app_base.debug import DebugContext, debug_model_save

class MyModel(models.Model):
    # Option 1: Decorator on save()
    @debug_model_save("save")
    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)

    # Option 2: Manual logging in critical method
    def custom_operation(self):
        with DebugContext.section("My operation"):
            DebugContext.log("Step 1")
            # ... code ...
            DebugContext.success("Complete")
```

### Add Logging to Views

```python
from apps.app_base.debug import debug_view

# Option 1: Decorator
@debug_view
def my_view(request):
    ...

# Option 2: Manual sections
def my_view(request):
    with DebugContext.section("Processing form", {"user": request.user.username}):
        # ... code ...
```

### Add Logging to Signals

```python
from apps.app_base.debug import debug_signal

@receiver(post_save, sender=MyModel)
@debug_signal("post_save")
def handle_save(sender, instance, created, **kwargs):
    # Automatically logged as 📡 signal handler
    ...
```

---

## Log Rotation & Archival

Logs are automatically rotated when they exceed 10MB:
- **debug.log** → debug.log.1, debug.log.2, ... (keeps 10 backups)
- **audit.log** → audit.log.1, audit.log.2, ... (keeps 20 backups for compliance)
- **errors.log** → errors.log.1, errors.log.2, ... (keeps 10 backups)

**For compliance**, archive logs periodically:
```bash
# Archive old logs
tar czf logs_2026_04.tar.gz logs/*.log.*
rm logs/*.log.*
```

---

## Performance Considerations

### ✅ Safe to Log
- Operation names and IDs
- Timing data
- User information
- Status codes
- Count of affected records

### ❌ Never Log
- Passwords or secrets (AUTH_USER logs are filtered)
- Personal identifying information (PII)
- Raw form data (log only field names)
- Full request bodies (log only size/type)
- Database query strings (too verbose)

### Optimize for High-Volume
```python
# ✅ Good: Summarize instead of logging details
DebugContext.audit("bulk_update", "Product", None, 
    details={"count": 1000, "fields": ["status"]})

# ❌ Bad: Don't log every item
for product in products:
    DebugContext.audit("product_updated", "Product", product.pk)
```

---

## Troubleshooting

### "Logs not appearing"
1. Check Django DEBUG setting
2. Ensure `logs/` directory is writable
3. Check logger name matches: `farm_debug`, `farm_audit`
4. Verify handler configuration in settings.py

### "Audit log entries are incomplete"
1. Ensure `user` parameter is passed to `audit()`
2. Check exception is not preventing audit call
3. Verify `_configure_audit_handler()` runs once on first call

### "Logs growing too large"
1. Increase `maxBytes` in settings.py (currently 10MB)
2. Decrease `backupCount` to keep fewer backups
3. Implement log archival script (see above)

---

## Summary

| Component | Purpose | File | Trigger |
|-----------|---------|------|---------|
| **DebugContext** | Structured logging with timing | apps/app_base/debug.py | Manual or decorator |
| **Audit Trail** | Compliance-grade event logging | logs/audit.log | DebugContext.audit() |
| **Middleware** | HTTP request/response tracking | farm/middlewares_audit.py | Every HTTP request |
| **QuerySet Logging** | Bulk operation tracking | apps/app_base/queryset_logging.py | LoggingManager usage |
| **Error Log** | Exception capture | logs/errors.log | Automatic on errors |

**Bottom Line**: Use `DebugContext` everywhere — it provides both real-time debugging AND permanent audit trails without extra effort.
