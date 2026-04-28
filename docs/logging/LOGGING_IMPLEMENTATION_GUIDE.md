# Logging Implementation Guide - What to Apply Next

This guide shows **exactly** which files need logging added and provides ready-to-use code snippets.

---

## Priority 1: Critical Financial Operations ⚠️

### 1. Operation Model (`apps/app_operation/models.py`)

**Status**: Likely missing comprehensive logging
**Why**: All operations affect financial state, inventory, and entity status

**Add to imports**:
```python
from apps.app_base.debug import DebugContext, debug_transaction
```

**Add to Operation.save()**:
```python
def save(self, *args, **kwargs):
    action = "update" if self.pk else "create"
    with DebugContext.section(f"Operation.{action}", {
        "type": self.operation_type,
        "entity": str(self.entity),
        "status": self.status,
    }):
        try:
            result = super().save(*args, **kwargs)
            DebugContext.success(f"Operation {action}d", {"pk": self.pk})
            
            # Audit the operation
            DebugContext.audit(
                action=f"operation_{action}",
                entity_type="Operation",
                entity_id=self.pk,
                details={"type": self.operation_type, "status": self.status},
                user=str(self.officer) if hasattr(self, 'officer') else "system"
            )
            return result
        except Exception as e:
            DebugContext.error(f"Operation {action} failed", e)
            raise
```

**Add to Operation.delete()**:
```python
def delete(self, *args, **kwargs):
    with DebugContext.section("Operation.delete", {"pk": self.pk, "type": self.operation_type}):
        DebugContext.warn("Deleting operation", {
            "pk": self.pk,
            "type": self.operation_type,
            "status": self.status,
        })
        
        DebugContext.audit(
            action="operation_deleted",
            entity_type="Operation",
            entity_id=self.pk,
            details={"type": self.operation_type},
            user="system"
        )
        
        return super().delete(*args, **kwargs)
```

**Add status transition logging**:
```python
def update_status(self, new_status, reason=""):
    """Log status transitions."""
    old_status = self.status
    self.status = new_status
    
    with DebugContext.section("Operation.status_change", {
        "pk": self.pk,
        "old_status": old_status,
        "new_status": new_status,
        "reason": reason,
    }):
        self.save()
        
        DebugContext.audit(
            action="operation_status_changed",
            entity_type="Operation",
            entity_id=self.pk,
            details={
                "from_status": old_status,
                "to_status": new_status,
                "reason": reason,
            },
            user="system"
        )
```

---

### 2. Adjustment Model (`apps/app_adjustment/models.py`)

**Status**: Likely missing logging
**Why**: Adjustments are corrections/reversals affecting inventory and financials

**Add to imports**:
```python
from apps.app_base.debug import DebugContext
```

**Add to Adjustment.save()**:
```python
def save(self, *args, **kwargs):
    action = "update" if self.pk else "create"
    with DebugContext.section(f"Adjustment.{action}", {
        "type": getattr(self, "adjustment_type", "unknown"),
        "operation": str(self.operation),
        "reason": getattr(self, "reason", ""),
    }):
        result = super().save(*args, **kwargs)
        
        DebugContext.audit(
            action=f"adjustment_{action}",
            entity_type="Adjustment",
            entity_id=self.pk,
            details={
                "operation": str(self.operation),
                "reason": getattr(self, "reason", ""),
            },
            user="system"
        )
        
        return result
```

---

### 3. Inventory Model (`apps/app_inventory/models.py`)

**Status**: Needs enhanced logging
**Why**: Inventory changes are critical for operations tracking

**Add to imports**:
```python
from apps.app_base.debug import DebugContext
```

**Add to Inventory movement methods**:
```python
def add_inventory(self, quantity, source="", reason=""):
    """Log inventory increase."""
    with DebugContext.section("Inventory.add", {
        "product": str(self.product),
        "quantity": quantity,
        "reason": reason,
    }):
        old_qty = self.quantity
        self.quantity += quantity
        self.save()
        
        DebugContext.success("Inventory added", {
            "old_qty": old_qty,
            "new_qty": self.quantity,
            "added": quantity,
        })
        
        DebugContext.audit(
            action="inventory_added",
            entity_type="Inventory",
            entity_id=self.pk,
            details={
                "product": str(self.product),
                "quantity": quantity,
                "reason": reason,
                "old_qty": old_qty,
                "new_qty": self.quantity,
            },
            user=source or "system"
        )

def remove_inventory(self, quantity, reason=""):
    """Log inventory decrease."""
    with DebugContext.section("Inventory.remove", {
        "product": str(self.product),
        "quantity": quantity,
        "reason": reason,
    }):
        if self.quantity < quantity:
            DebugContext.error("Insufficient inventory", {
                "current": self.quantity,
                "requested": quantity,
                "shortage": quantity - self.quantity,
            })
            raise ValueError(f"Insufficient inventory: have {self.quantity}, need {quantity}")
        
        old_qty = self.quantity
        self.quantity -= quantity
        self.save()
        
        DebugContext.success("Inventory removed", {
            "old_qty": old_qty,
            "new_qty": self.quantity,
            "removed": quantity,
        })
        
        DebugContext.audit(
            action="inventory_removed",
            entity_type="Inventory",
            entity_id=self.pk,
            details={
                "product": str(self.product),
                "quantity": quantity,
                "reason": reason,
                "old_qty": old_qty,
                "new_qty": self.quantity,
            },
            user="system"
        )
```

---

## Priority 2: Critical Views 🌐

### 1. Operation Create/Update Views (`apps/app_operation/views/`)

**Status**: Likely needs logging
**Why**: Entry points for all data changes

**Template**:
```python
from apps.app_base.debug import DebugContext, debug_view

@debug_view  # Automatically logs request metadata
def operation_create(request):
    with DebugContext.section("Creating new operation", {"user": request.user.username}):
        if request.method == "POST":
            form = OperationForm(request.POST)
            
            with DebugContext.section("Form validation"):
                if form.is_valid():
                    DebugContext.success("Form valid")
                    
                    with DebugContext.section("Saving operation"):
                        operation = form.save(commit=False)
                        operation.officer = request.user
                        operation.save()
                        
                        DebugContext.audit(
                            action="operation_created_via_ui",
                            entity_type="Operation",
                            entity_id=operation.pk,
                            details={
                                "type": operation.operation_type,
                                "entity": str(operation.entity),
                            },
                            user=request.user.username
                        )
                        
                        return redirect('operation_detail', pk=operation.pk)
                else:
                    DebugContext.error("Form invalid", data={
                        "errors": dict(form.errors),
                    })
    
    return render(request, "operation_form.html", {"form": form})
```

### 2. Transaction Create Views (`apps/app_transaction/views/`)

**Status**: Likely needs logging
**Why**: Transactions are critical financial records

**Template**:
```python
from apps.app_base.debug import DebugContext, debug_view

@debug_view
def transaction_create(request, operation_pk):
    with DebugContext.section("Creating transaction", {
        "operation_pk": operation_pk,
        "user": request.user.username,
    }):
        operation = get_object_or_404(Operation, pk=operation_pk)
        
        if request.method == "POST":
            form = TransactionForm(request.POST)
            
            if form.is_valid():
                source = form.cleaned_data['source']
                target = form.cleaned_data['target']
                amount = form.cleaned_data['amount']
                
                with DebugContext.section("Transaction.create()", {
                    "source": str(source),
                    "target": str(target),
                    "amount": float(amount),
                }):
                    try:
                        transaction = Transaction.create(
                            source=source,
                            target=target,
                            document=operation,
                            tx_type=TransactionType.OPERATION,
                            amount=amount,
                            officer=request.user,
                        )
                        
                        DebugContext.success("Transaction created via UI", {
                            "transaction_pk": transaction.pk,
                        })
                        
                        return redirect('transaction_detail', pk=transaction.pk)
                    except ValidationError as e:
                        DebugContext.error("Transaction creation failed", e)
                        form.add_error(None, str(e))
            else:
                DebugContext.error("Form invalid", data=dict(form.errors))
    
    return render(request, "transaction_form.html", {"form": form, "operation": operation})
```

### 3. Entity Create/Update Views (`apps/app_entity/views/`)

**Status**: Likely needs logging
**Why**: Entities are foundational data affecting all operations

**Template**:
```python
from apps.app_base.debug import DebugContext, debug_view

@debug_view
def person_create(request):
    with DebugContext.section("Creating new person entity", {"user": request.user.username}):
        if request.method == "POST":
            form = PersonForm(request.POST)
            
            if form.is_valid():
                person = form.save()
                
                DebugContext.audit(
                    action="entity_created",
                    entity_type="Person",
                    entity_id=person.pk,
                    details={
                        "name": person.get_full_name() if hasattr(person, 'get_full_name') else str(person),
                        "type": "Person",
                    },
                    user=request.user.username
                )
                
                return redirect('entity_detail', pk=person.pk)
            else:
                DebugContext.error("Person form invalid", data=dict(form.errors))
    
    return render(request, "person_form.html", {"form": form})
```

---

## Priority 3: Signal Handlers 📡

### Location: `apps/app_operation/signals.py`

**Status**: Partially implemented (initial_period signal has logging)
**What to add**:

```python
from apps.app_base.debug import DebugContext, debug_signal

@receiver(post_save, sender=Transaction)
@debug_signal("Transaction.post_save")
def handle_transaction_save(sender, instance, created, **kwargs):
    """Log all transaction saves and trigger cascading updates."""
    action = "created" if created else "updated"
    
    with DebugContext.section(f"Transaction.post_save ({action})", {
        "pk": instance.pk,
        "type": instance.type,
        "amount": float(instance.amount),
    }):
        # Update inventory if needed
        if hasattr(instance, 'document'):
            DebugContext.log("Updating associated document state")
            # ... update document ...
        
        DebugContext.success(f"Transaction post-save complete")

@receiver(post_delete, sender=Operation)
@debug_signal("Operation.post_delete")
def handle_operation_delete(sender, instance, **kwargs):
    """Log operation deletions."""
    DebugContext.warn(f"Operation deleted: {instance.pk}", {
        "type": instance.operation_type,
        "entity": str(instance.entity),
    })
```

---

## Priority 4: Query Optimization with LoggingQuerySet

### Use in Models

**Current**:
```python
class Product(models.Model):
    objects = models.Manager()
```

**Enhanced**:
```python
from apps.app_base.queryset_logging import LoggingManager

class Product(models.Model):
    objects = LoggingManager()  # All QuerySet operations are now logged
```

**This automatically logs**:
- `Product.objects.filter(...).delete()` → bulk_delete audit log
- `Product.objects.bulk_update(...)` → bulk_update audit log
- `Product.objects.bulk_create(...)` → bulk_create audit log

---

## Implementation Checklist

- [ ] **Operation model**: Add save(), delete(), status_change() logging
- [ ] **Adjustment model**: Add logging to save(), delete()
- [ ] **Inventory model**: Add add_inventory(), remove_inventory() logging
- [ ] **Transaction model**: DONE ✅
- [ ] **Operation create view**: Add logging
- [ ] **Transaction create view**: Add logging
- [ ] **Entity create/update views**: Add logging
- [ ] **Signal handlers**: Add complete logging
- [ ] **All models**: Convert to LoggingManager
- [ ] **Test audit trail**: Verify logs/audit.log has entries
- [ ] **Test error logging**: Verify logs/errors.log captures exceptions

---

## Quick Testing

After implementing logging, verify it works:

```bash
# 1. Check log files created
ls -lah logs/

# 2. Create a test transaction
python manage.py shell
>>> from apps.app_entity.models import Entity
>>> from apps.app_transaction.models import Transaction
>>> # ... create test transaction ...

# 3. Verify audit log
tail -20 logs/audit.log | jq .

# 4. Verify debug log
tail -30 logs/debug.log
```

**Expected output in logs/audit.log**:
```json
{"action": "transaction_created", "entity_type": "Transaction", "entity_id": 1, ...}
```

**Expected output in logs/debug.log**:
```
INFO | 2026-04-28 14:25:31 | farm_debug | Transaction.create()
INFO | 2026-04-28 14:25:31 |        ✓ Transaction created | {"transaction_pk": 1}
```

---

## Common Patterns

### ✅ Logging a State Transition
```python
def mark_as_sold(self):
    old_status = self.status
    self.status = "SOLD"
    self.save()
    
    DebugContext.audit(
        action="product_sold",
        entity_type="Product",
        entity_id=self.pk,
        details={"from_status": old_status, "to_status": "SOLD"},
        user="system"
    )
```

### ✅ Logging a Complex Operation
```python
import uuid

def process_batch(self, items):
    batch_id = f"batch_{uuid.uuid4().hex[:8]}"
    DebugContext.transaction_start(batch_id, f"Processing {len(items)} items", {
        "count": len(items),
    })
    
    try:
        for item in items:
            # ... process ...
        
        DebugContext.transaction_commit(batch_id, {"status": "success", "count": len(items)})
    except Exception as e:
        DebugContext.transaction_rollback(batch_id, str(e), e)
        raise
```

### ✅ Logging User Action in View
```python
@debug_view
def approve_operation(request, operation_pk):
    operation = get_object_or_404(Operation, pk=operation_pk)
    operation.approve()
    
    DebugContext.audit(
        action="operation_approved",
        entity_type="Operation",
        entity_id=operation.pk,
        details={"type": operation.operation_type},
        user=request.user.username
    )
    
    return redirect(...)
```

---

## Need Help?

1. **See actual usage**: Check `apps/app_transaction/models.py` for Transaction model logging
2. **See signal logging**: Check `apps/app_operation/signals.py` for signal decoration
3. **See middleware**: Check `farm/middlewares_audit.py` for HTTP request logging
4. **See documentation**: Read `LOGGING_STANDARDS.md` for complete reference

Start with Priority 1 operations and work down. Each file should take 10-15 minutes to add logging.
