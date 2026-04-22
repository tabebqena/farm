# Inventory Ledger System
> Append-only ledger for tracking all inventory changes and stock status queries.

---

## Overview

`ProductLedgerEntry` is an immutable ledger that records every inventory event (purchase, sale, consumption, death, adjustments, etc.) as a separate row. Point-in-time inventory state is computed by summing delta values up to a cutoff date.

This spec documents the complete ledger system and query capabilities.

---

## Ledger Entry Types

All inventory-changing operations map to one of these entry types:

| Type | Sign Convention | Operations | Use Case |
|------|---|---|---|
| `PURCHASE` | qty: +1, value: +1 | PURCHASE | Stock received |
| `SALE` | qty: -1, value: -1 | SALE | Stock sold/dispatched |
| `BIRTH` | qty: +1, value: +1 | BIRTH | Animals born/produced |
| `DEATH` | qty: -1, value: -1 | DEATH | Animals died |
| **`CONSUMPTION`** | qty: -1, value: -1 | CONSUMPTION | Feed/medicine consumed |
| `CAPITAL_GAIN` | qty: 0, value: +1 | CAPITAL_GAIN | Unrealized appreciation |
| `CAPITAL_LOSS` | qty: 0, value: -1 | CAPITAL_LOSS | Unrealized depreciation |
| `REVERSAL` | negates prior | All (reverse) | Undoes a recorded entry |
| `ADJUSTMENT` | per-line deltas | ADJUSTMENT | Corrects recorded entries |

**Status:** ✅ CONSUMPTION added to EntryType choices (migration 0002)

---

## Entry Recording

### ProductLedgerEntry.record(operation, negate=False)

Records ledger entries for all products linked to an operation.

**Called after:**
- Operation and InvoiceItems are fully committed
- All Product M2M links are persisted

**Returns:** `(created_count, skipped_count)` — enables idempotent replay

**Example (Purchase):**
```python
purchase_op = Operation.objects.create(
    operation_type=OperationType.PURCHASE,
    date=date(2026, 4, 15),
    entity=farm
)
item = InvoiceItem.objects.create(
    operation=purchase_op,
    product=ProductTemplate.objects.get(name="Fattening Calves"),
    quantity=10,
    unit_price=Decimal("500.00")
)
product = Product.objects.create(
    entity=farm,
    product_template=item.product,
    unit_price=item.unit_price
)
item.products.add(product)

# Ledger records: +10 qty, +5000 value
created, skipped = ProductLedgerEntry.record(purchase_op)
# created=1, skipped=0 (idempotency_key prevents duplicates)
```

**Consumption Entry (NEW):**
```python
consumption_op = Operation.objects.create(
    operation_type=OperationType.CONSUMPTION,
    date=date(2026, 4, 20),
    entity=farm
)
item = InvoiceItem.objects.create(
    operation=consumption_op,
    product=ProductTemplate.objects.get(nature="FEED"),  # Only FEED/MEDICINE allow CONSUMPTION
    quantity=50,  # 50 kg consumed
    unit_price=Decimal("2.00")  # Cost per kg
)
product = Product.objects.filter(entity=farm, product_template=item.product).first()
item.products.add(product)

# Ledger records: -50 qty, -100 value
ProductLedgerEntry.record(consumption_op)
```

---

## Inventory Queries

### ProductLedgerEntry.state_as_of(product, as_of)

Get point-in-time quantity and value for a single product.

**Returns:** `{"quantity": Decimal, "value": Decimal}`

```python
state = ProductLedgerEntry.state_as_of(
    product=calf_product,
    as_of=date(2026, 4, 30)
)
# state = {
#   "quantity": Decimal("25.50"),  # Sum of all qty_deltas up to 2026-04-30
#   "value": Decimal("12750.00")   # Sum of all value_deltas
# }
```

---

### ProductLedgerEntry.portfolio_as_of(entity, as_of)

Get all products still in stock (qty > 0) for an entity at a point in time.

**Returns:** QuerySet of dicts with keys: `product_id`, `quantity`, `value`

```python
portfolio = ProductLedgerEntry.portfolio_as_of(
    entity=farm,
    as_of=date(2026, 4, 30)
)
for item in portfolio:
    print(f"Product {item['product_id']}: {item['quantity']} units worth {item['value']}")

# Output:
# Product 42: 25.50 units worth 12750.00
# Product 45: 100.00 units worth 5000.00
# (Only products with qty > 0 appear)
```

---

### ProductLedgerEntry.pending_deliveries(entity=None, as_of=None) ✨ NEW

Get all PURCHASE line items where the delivered quantity is less than ordered quantity.

**Filters:**
- `entity` (optional): Restrict to specific project/farm entity
- `as_of` (optional): Only include operations up to this date

**Returns:** QuerySet of dicts with keys:
- `id` — InvoiceItem ID
- `quantity` — Ordered quantity
- `delivered_qty` — Sum of all non-reversed InventoryMovementLine quantities
- `pending_qty` — `quantity - delivered_qty`
- `product__name` — Product template name
- `operation__id` — Purchase operation ID

**Use Case:** Monitor what's been ordered but not yet received

```python
# All pending deliveries for the farm
pending = ProductLedgerEntry.pending_deliveries(entity=farm)
# [
#   {
#     'id': 15,
#     'quantity': Decimal('100.00'),
#     'delivered_qty': Decimal('60.00'),
#     'pending_qty': Decimal('40.00'),
#     'product__name': 'Fattening Calves',
#     'operation__id': 123
#   },
#   ...
# ]

# As of a specific date
pending = ProductLedgerEntry.pending_deliveries(
    entity=farm,
    as_of=date(2026, 4, 15)
)

# Iterate to check delivery status
for item in pending:
    print(f"{item['product__name']}: {item['pending_qty']} units still pending")
```

**Implementation Details:**
- Filters `InventoryMovementLine` to exclude reversals (`reversal_of__isnull=True`)
- Uses `Coalesce` to default missing movement sums to 0
- Orders results by operation date

---

## Data Consistency Guarantees

### Idempotency

Each ledger entry has a unique `idempotency_key` computed from operation and product:

```
"item_{item.pk}_product_{product.pk}"
"rev_item_{item.pk}_product_{product.pk}"  # For reversals
"adj_line_{line.pk}_product_{product.pk}"  # For adjustments
"movement_line_{line.pk}_product_{product.pk}"  # For movements
```

**guarantees:**
- Replaying an operation creates no duplicates
- Database-level unique constraint prevents accidents
- Safe to call `ProductLedgerEntry.record()` multiple times

### Immutability

Ledger entries are **never updated or deleted** — only appended.

- Reversals create new rows with negated deltas
- Adjustments create new rows with delta corrections
- Old entries remain for audit trail

---

## Supported Product Natures

| Nature | Allowed Operations | Use Cases |
|--------|---|---|
| `ANIMAL` | PURCHASE, SALE, BIRTH, DEATH, CAPITAL_GAIN, CAPITAL_LOSS | Livestock |
| `FEED` | PURCHASE, SALE, **CONSUMPTION**, CAPITAL_GAIN, CAPITAL_LOSS | Feed stock |
| `MEDICINE` | PURCHASE, SALE, **CONSUMPTION**, CAPITAL_GAIN, CAPITAL_LOSS | Drugs/medicines |
| `PRODUCT` | PURCHASE, SALE, CAPITAL_GAIN, CAPITAL_LOSS | Production output |

---

## Changes Made

### File: `apps/app_inventory/models.py`

**1. Added CONSUMPTION to EntryType (line 35)**
```python
class EntryType(models.TextChoices):
    # ... existing types ...
    CONSUMPTION = "CONSUMPTION", _("Consumption")
```

**2. Updated _MAP in ProductLedgerEntry.record() (line 87)**
```python
_MAP = {
    # ... existing mappings ...
    OperationType.CONSUMPTION: (cls.EntryType.CONSUMPTION, -1, -1),
}
```
Signs: `qty_sign=-1` (removes stock), `val_sign=-1` (reduces value)

**3. Added pending_deliveries() class method (line 293–336)**
- Queries PURCHASE operations with incomplete deliveries
- Annotates `delivered_qty` and `pending_qty`
- Supports optional entity and date filters

### Migration: `0002_alter_productledgerentry_entry_type`

Updates the `entry_type` field choices to include `CONSUMPTION`.

---

## Testing

Run the test suite:
```bash
python manage.py test apps.app_inventory
```

Manual verification:
```bash
python manage.py shell
>>> from apps.app_inventory.models import ProductLedgerEntry
>>> # CONSUMPTION in choices
>>> "CONSUMPTION" in dict(ProductLedgerEntry.EntryType.choices)
True
>>> # pending_deliveries callable
>>> ProductLedgerEntry.pending_deliveries()
<QuerySet [...]>
```

---

## Future Enhancements

- [ ] Batch create ledger entries for bulk operations
- [ ] Inventory valuation methods (FIFO, LIFO, weighted average)
- [ ] Stock level alerts/thresholds
- [ ] Consumption forecasting based on historical trends
- [ ] Integration with financial reporting (cost of goods sold)
