# Debug Logging Quick Reference

## TL;DR - Get Started in 30 Seconds

```python
# Import debug utilities
from apps.app_base.debug import DebugContext, debug_view, debug_function

# Use in your view
@debug_view
def my_view(request):
    with DebugContext.section("Processing payment", {"amount": 1000}):
        # Your code here
        DebugContext.log("Step 1 complete")
        DebugContext.success("Payment processed")

# Or use in any function
@debug_function
def process_something(data):
    # Auto-logged with timing
    return result

# Manual logging
DebugContext.log("Info message", {"key": "value"})
DebugContext.warn("Warning", {"context": "data"})
DebugContext.error("Error occurred", exception_obj)
DebugContext.success("Done", {"result": "value"})
```

## Status Symbols

| Symbol | Meaning | Use Case |
|--------|---------|----------|
| ✓ | Success | `DebugContext.success()` |
| ❌ | Error | `DebugContext.error()` |
| ⚡ | Info | `DebugContext.log()` |
| → | Start section | Context manager entry |
| ← | End section | Context manager exit |
| 🌐 | HTTP view | `@debug_view` decorated |
| 🔵 | Function | `@debug_function` decorated |
| 📡 | Signal | `@debug_signal` decorated |
| 💾 | Database | `@debug_model_save` decorated |

## Common Patterns

### Pattern 1: Atomic Operation with Steps
```python
with DebugContext.section("Complex operation", {"id": obj.pk}):
    DebugContext.log("Step 1: Validation")
    validate_data()
    DebugContext.success("Step 1 complete")
    
    DebugContext.log("Step 2: Processing")
    process_data()
    DebugContext.success("Step 2 complete")
    
    DebugContext.log("Step 3: Saving")
    obj.save()
    DebugContext.success("All steps complete")
```

**Output**:
```
→ Complex operation | {"id": 123}
  ⚡ Step 1: Validation
  ✓ Step 1 complete
  ⚡ Step 2: Processing
  ✓ Step 2 complete
  ⚡ Step 3: Saving
  ✓ All steps complete
← Complex operation (0.234s)
```

### Pattern 2: Conditional Logging
```python
item_count = items.count()
DebugContext.log(f"Processing {item_count} items", {
    "item_count": item_count,
    "items": [item.name for item in items[:5]],  # First 5
})

for item in items:
    if item.is_critical:
        DebugContext.warn(f"Critical item: {item.name}")
    else:
        DebugContext.log(f"Processing item: {item.name}")
```

### Pattern 3: Error Handling
```python
try:
    result = dangerous_operation()
    DebugContext.success("Operation completed", {"result": result})
except ValueError as e:
    DebugContext.error("Invalid value provided", e, {
        "expected": "positive number",
        "received": str(e),
    })
    raise
except Exception as e:
    DebugContext.error("Unexpected error", e)
    raise
```

### Pattern 4: Loop Monitoring
```python
total = Decimal("0")
for i, item in enumerate(items):
    value = item.compute_value()
    total += value
    
    if i % 10 == 0:
        DebugContext.log(f"Progress: {i}/{items.count()}", {
            "current_total": float(total),
            "progress_percent": int(100 * i / items.count()),
        })

DebugContext.success(f"Processed {items.count()} items", {
    "total": float(total),
    "average": float(total / items.count()),
})
```

## API Reference

### DebugContext.log()
```python
DebugContext.log(message: str, data: Optional[Dict] = None, level: str = "info")

# Examples
DebugContext.log("User logged in")
DebugContext.log("Purchase created", {"amount": 1000, "vendor": "ACME"})
DebugContext.log("Unusual behavior detected", {"threshold": 5, "actual": 15}, level="warning")
```

### DebugContext.warn()
```python
DebugContext.warn(message: str, data: Optional[Dict] = None)

# Examples
DebugContext.warn("Vendor has no address")
DebugContext.warn("Amount exceeds budget", {"budget": 10000, "amount": 12000})
```

### DebugContext.error()
```python
DebugContext.error(message: str, exception: Optional[Exception] = None, data: Optional[Dict] = None)

# Examples
DebugContext.error("Failed to save")
DebugContext.error("Validation failed", validation_error, {"field": "amount"})
```

### DebugContext.success()
```python
DebugContext.success(message: str, data: Optional[Dict] = None)

# Examples
DebugContext.success("Purchase complete")
DebugContext.success("All items processed", {"count": 42, "total": 5000})
```

### DebugContext.section()
```python
with DebugContext.section(title: str, data: Optional[Dict] = None):
    # Code block runs with automatic indentation and timing
    ...

# Examples
with DebugContext.section("Database transaction", {"table": "operations"}):
    obj.save()
    obj.refresh_from_db()
```

## Decorators

### @debug_view
```python
from apps.app_base.debug import debug_view
from django.http import HttpResponse

@debug_view
def my_view(request, id):
    # Automatically logs HTTP method, path, user, params
    # Logs response status code
    return HttpResponse("OK")
```

### @debug_function
```python
from apps.app_base.debug import debug_function

@debug_function
def calculate_total(items):
    # Automatically logs function name, args (first 3), kwargs
    # Logs timing and completion
    return sum(item.amount for item in items)
```

### @debug_model_save
```python
from apps.app_base.debug import debug_model_save

class MyModel(BaseModel):
    @debug_model_save("my_custom_save")
    def save(self, *args, **kwargs):
        # Automatically logs create vs update
        # Logs pk, model name, update_fields
        super().save(*args, **kwargs)
```

### @debug_signal
```python
from apps.app_base.debug import debug_signal
from django.db.models.signals import post_save

@debug_signal("post_save")
def my_signal_handler(sender, instance, **kwargs):
    # Automatically logs signal name
    # Logs sender class name
    # Logs signal kwargs keys
    ...
```

## Data Formatting Guidelines

### What to Log
✓ **DO log**:
- Simple values: `{"count": 5, "amount": 100.50}`
- String representations: `{"user": "john", "vendor": "ACME"}`
- Boolean states: `{"is_new": true, "is_active": false}`
- Timestamps: `{"date": "2026-04-22", "time": "14:30:00"}`
- Foreign keys: `{"operation_pk": 123, "user_pk": 456}`

✗ **DON'T log**:
- Full object representations (use str() or name instead)
- Passwords or sensitive data
- Large collections (use count instead: `{"items": 42}` not `{"items": [...]}`
- Raw exception objects (let error() handle them)

### Example Good Data
```python
# ✓ Good
DebugContext.log("Operation created", {
    "operation_pk": 123,
    "operation_type": "PURCHASE",
    "source": "Project A",
    "destination": "Vendor B",
    "amount": 5000.50,
    "date": "2026-04-22",
})

# ✗ Bad
DebugContext.log("Operation created", {
    "operation": operation_obj,  # Don't log full object
    "items": [item1, item2, item3],  # Don't log collections
    "password": "secret123",  # Don't log sensitive data
})
```

## Viewing Logs

### Django Development Server
```bash
# Terminal 1: Run server (logs to console)
python manage.py runserver

# You'll see color-coded output with indentation and timing
```

### Django Shell
```bash
# Terminal
python manage.py shell

# Import and use
from apps.app_base.debug import DebugContext
from apps.app_adjustment.models import InvoiceItemAdjustment

adj = InvoiceItemAdjustment.objects.get(pk=1)
adj.finalize()  # Watch debug output

# Logs appear in the same terminal
```

### Django Management Commands
```bash
# Logs appear on stdout
python manage.py migrate
python manage.py test
```

### Log Files (if configured)
```bash
# In settings.py:
# Redirect to file handler for persistent logs
tail -f /var/log/django/farm_debug.log
```

## Performance Profiling

### Time Sections to Find Bottlenecks
```python
with DebugContext.section("Database query batch", {"count": 1000}):
    # Expensive operation
    results = Item.objects.filter(...).update(...)
    # See elapsed time: (0.523s)
```

### Compare Operations
```python
# Approach A
with DebugContext.section("Approach A"):
    # ... code ...
# Output: (0.234s)

# Approach B  
with DebugContext.section("Approach B"):
    # ... alternative code ...
# Output: (0.156s)
# → Approach B is faster by 0.078s
```

## Common Issues & Solutions

### "AttributeError: 'NoneType' has no attribute..."
```python
# Problem: Trying to log None
data = None
DebugContext.log("Got data", {"data": data})  # Error if data is None

# Solution: Check first
if data:
    DebugContext.log("Got data", {"data": data})
else:
    DebugContext.warn("No data returned")
```

### "Dict not JSON serializable"
```python
# Problem: Complex objects in data dict
DebugContext.log("Item", {"item": item_obj})  # May fail

# Solution: Convert to string first
DebugContext.log("Item", {"item": str(item_obj), "item_pk": item_obj.pk})
```

### "Logs not appearing"
```python
# Check: Is DEBUG=True?
# Check: Logger level is DEBUG or lower?

# Test: 
from apps.app_base.debug import DebugContext
DebugContext.log("TEST MESSAGE")  # Should appear on console

# If not visible:
import logging
logging.getLogger('farm_debug').setLevel(logging.DEBUG)
```

## Best Practices

1. **Be Specific**: Use operation-specific names
   - ✓ "Processing invoice items for purchase"
   - ✗ "Processing"

2. **Include Context**: Always add relevant data
   - ✓ `{"operation_pk": 123, "item_count": 5}`
   - ✗ No data dict

3. **Use Appropriate Levels**: Match message to severity
   - `.log()` - Normal operations
   - `.warn()` - Unusual but handled
   - `.error()` - Errors (with exception)
   - `.success()` - Important milestones

4. **Section Large Operations**: Break complex flows into sections
   ```python
   with DebugContext.section("Entire purchase flow"):
       with DebugContext.section("Step 1: Validation"):
           ...
       with DebugContext.section("Step 2: Creation"):
           ...
   ```

5. **Don't Overlog**: Only log key points, not every line
   - ✓ Entry/exit of important functions
   - ✓ State transitions and decisions
   - ✓ Error conditions
   - ✗ Every loop iteration
   - ✗ Every variable assignment

## Real-World Examples from the Codebase

### Example 1: Purchase Wizard (Multiple Steps)
```python
@debug_view
def purchase_wizard_view(request, pk, operation_pk=None, step=1):
    DebugContext.log("Wizard initialized", {"step": step})
    
    project = get_object_or_404(Entity, pk=pk)
    DebugContext.log("Project loaded", {"project": str(project)})
    
    if request.method == "POST":
        DebugContext.log("Dispatching POST", {"step": step})
        return _handle_step_post(request, project)
    
    DebugContext.success(f"Rendering step {step}")
    return render(...)
```

### Example 2: Complex Adjustment Finalization
```python
def finalize(self):
    with DebugContext.section("Finalize adjustment", {"pk": self.pk}):
        lines = self.lines.all()
        total = sum(line.delta for line in lines)
        
        DebugContext.log("Computed delta", {"total": float(total)})
        
        if total == 0:
            DebugContext.error("Zero delta")
            raise ValueError("...")
        
        adj = Adjustment.objects.create(...)
        DebugContext.success("Adjustment created", {"adj_pk": adj.pk})
```

### Example 3: Loop with Progress
```python
def process_items(items):
    with DebugContext.section("Bulk process", {"count": items.count()}):
        for i, item in enumerate(items):
            if i % 100 == 0:
                DebugContext.log(f"Progress", {
                    "processed": i,
                    "remaining": items.count() - i,
                })
            item.process()
        DebugContext.success(f"All {items.count()} processed")
```

## Additional Resources

- **Full guide**: `PROJECT_WALKTHROUGH.md`
- **Debug module**: `apps/app_base/debug.py`
- **Examples**: Search for `DebugContext` in:
  - `apps/app_operation/views/purchase_wizard.py`
  - `apps/app_operation/models/operation.py`
  - `apps/app_adjustment/models.py`
  - `apps/app_operation/signals.py`
