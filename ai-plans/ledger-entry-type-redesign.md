# ProductLedgerEntry — Issuance vs Movement Type Redesign

## Problem Statement

Under the current lazy-Product-creation architecture:

1. **`unreceived_purchases()` and `undelivered_sales()` use `.exclude()`** — if an InvoiceItem has *any* movement lines, it's excluded entirely. For a Purchase of 10 units where 3 have arrived, the remaining 7 are **invisible** on the stock page.

2. **`ProductLedgerEntry` uses a single `EntryType`** (e.g. `PURCHASE`) for both the contract obligation and the physical movement. There's no way to query "what was contracted but not yet delivered" from the ledger alone.

3. **Adjustments** are recorded with a separate `ADJUSTMENT` type — they represent contract changes but are stored as a different category, making it harder to compute the effective contract amount.

## Proposed Principle

Split `EntryType` into **issuance** (contract/obligation) and **movement** (physical transfer) variants. At operation creation time, write **issuance** entries representing what was contracted. At movement time, write **movement** entries representing what physically moved.

**Pending quantity for any invoice item** = `SUM(issuance_entries) - SUM(movement_entries)`

The `Product` FK on issuance entries is **nullable** — since Products don't exist yet at contract time. Issuance entries link via `invoice_item` instead.

Movement entries store **both** `product` and `invoice_item` for full traceability.

---

## Affected Files

| File | Changes |
|------|---------|
| [`apps/app_inventory/models.py`](apps/app_inventory/models.py) | Schema change, write methods, query methods, EntryType enum |
| [`apps/app_operation/models/operation.py`](apps/app_operation/models/operation.py) | `save_inventory()` writes issuance entries |
| [`apps/app_operation/views/create.py`](apps/app_operation/views/create.py) | Minor — issuance flow through `_process_invoice()` |
| [`apps/app_inventory/views.py`](apps/app_inventory/views.py) | `stock_detail()` uses issuance - movement for pending |
| [`apps/app_adjustment/models.py`](apps/app_adjustment/models.py) | `record_adjustment_line()` writes issuance corrections |
| Tests | Update assertions to match new entry types |
| Data migration | Migrate existing entries to issuance/movement types |

---

## 1. Schema Change — `ProductLedgerEntry`

### Current

```python
product = models.ForeignKey("Product", on_delete=models.PROTECT, ...)
# No invoice_item FK
```

### New

```python
product = models.ForeignKey(
    "Product", on_delete=models.PROTECT,
    null=True, blank=True,            # <-- nullable for issuance entries
    related_name="ledger_entries",
)
invoice_item = models.ForeignKey(
    "app_inventory.InvoiceItem", on_delete=models.PROTECT,
    null=True, blank=True,            # <-- null for legacy rows, set for all new
    related_name="ledger_entries",
)
entry_type = models.CharField(
    max_length=30, choices=EntryType.choices  # <-- 30 chars for longer type names
)
```

**Why both nullable?** Issuance entries have `product=NULL, invoice_item=<item>`. Movement entries have `product=<product>, invoice_item=<item>`. Legacy migration entries may have `product=<product>, invoice_item=NULL`.

---

## 2. `EntryType` Enum — Split Into Issuance / Movement / Adjustment Variants

Following the `TransactionType` pattern, adjustments get their own types with the
**direction hardcoded in the name** — no runtime sign computation needed.

### New Enum

```python
class EntryType(models.TextChoices):
    # --- Issuance (contract) ---
    PURCHASE_ISSUANCE    = "PURCHASE_ISSUANCE",    _("Purchase Issuance")
    SALE_ISSUANCE        = "SALE_ISSUANCE",        _("Sale Issuance")
    BIRTH_ISSUANCE       = "BIRTH_ISSUANCE",       _("Birth Issuance")
    DEATH_ISSUANCE       = "DEATH_ISSUANCE",       _("Death Issuance")
    CONSUMPTION_ISSUANCE = "CONSUMPTION_ISSUANCE", _("Consumption Issuance")

    # --- Movement (physical) ---
    PURCHASE_MOVEMENT    = "PURCHASE_MOVEMENT",    _("Purchase Movement")
    SALE_MOVEMENT        = "SALE_MOVEMENT",        _("Sale Movement")
    BIRTH_MOVEMENT       = "BIRTH_MOVEMENT",       _("Birth Movement")
    DEATH_MOVEMENT       = "DEATH_MOVEMENT",       _("Death Movement")
    CONSUMPTION_MOVEMENT = "CONSUMPTION_MOVEMENT", _("Consumption Movement")

    # --- Adjustment (contract change) — direction is in the type name ---
    PURCHASE_ADJUSTMENT_INCREASE = "PURCHASE_ADJ_INC", _("Purchase Adjustment Increase")
    PURCHASE_ADJUSTMENT_DECREASE = "PURCHASE_ADJ_DEC", _("Purchase Adjustment Decrease")
    SALE_ADJUSTMENT_INCREASE     = "SALE_ADJ_INC",     _("Sale Adjustment Increase")
    SALE_ADJUSTMENT_DECREASE     = "SALE_ADJ_DEC",     _("Sale Adjustment Decrease")

    # --- Value-only (no quantity) ---
    CAPITAL_GAIN = "CAPITAL_GAIN", _("Capital Gain")
    CAPITAL_LOSS = "CAPITAL_LOSS", _("Capital Loss")

    REVERSAL = "REVERSAL", _("Reversal")
```

**Why separate adjustment types?** Adjustments modify the contract after creation.
By encoding direction into the type name (like `TransactionType` does with
`PURCHASE_ADJUSTMENT_INCREASE` / `PURCHASE_ADJUSTMENT_DECREASE`), the ledger
becomes self-documenting and query logic stays simple:

```sql
effective_issuance = SUM(PURCHASE_ISSUANCE)
                   + SUM(PURCHASE_ADJUSTMENT_INCREASE)
                   + SUM(PURCHASE_ADJUSTMENT_DECREASE)  -- negative
```

No runtime sign computation — the `val_sign` is always `+1` for increase types
and `-1` for decrease types.

### Usage per entry type

| Entry Type | `product` | `invoice_item` | Written by | When |
|-----------|-----------|----------------|-----------|------|
| `PURCHASE_ISSUANCE` | NULL | set | `record()` | Operation creation (`save_inventory()`) |
| `PURCHASE_MOVEMENT` | set | set | `record_movement_line()` | Movement creation |
| `SALE_ISSUANCE` | NULL | set | `record()` | Operation creation (`save_inventory()`) |
| `SALE_MOVEMENT` | set | set | `record_movement_line()` | Movement creation |
| `BIRTH_ISSUANCE` | NULL | set | `record()` | Operation creation (`save_inventory()`) |
| `BIRTH_MOVEMENT` | set | set | `record_movement_line()` | Movement creation |
| `DEATH_ISSUANCE` | **set** | set | `record()` | Operation creation (product IS selected) |
| `DEATH_MOVEMENT` | set | set | `record_movement_line()` | Movement creation |
| `CONSUMPTION_ISSUANCE` | set | set | `record()` | Operation creation (`save_inventory()`) |
| `CONSUMPTION_MOVEMENT` | set | set | `record_movement_line()` | Movement creation |
| `PURCHASE_ADJUSTMENT_INCREASE` | NULL | set | `record_adjustment_line()` | Line save (contract increase) |
| `PURCHASE_ADJUSTMENT_DECREASE` | NULL | set | `record_adjustment_line()` | Line save (contract decrease) |
| `SALE_ADJUSTMENT_INCREASE` | NULL | set | `record_adjustment_line()` | Line save (contract increase) |
| `SALE_ADJUSTMENT_DECREASE` | NULL | set | `record_adjustment_line()` | Line save (contract decrease) |
| `CAPITAL_GAIN` | set | set | `record()` | Operation creation |
| `CAPITAL_LOSS` | set | set | `record()` | Operation creation |
| `REVERSAL` | varies | varies | Any method with `negate=True` | Reversal |

### Sign conventions

| Entry Type | qty_sign | val_sign |
|-----------|----------|----------|
| `PURCHASE_ISSUANCE` | +1 | +1 |
| `PURCHASE_MOVEMENT` | +1 | +1 |
| `SALE_ISSUANCE` | -1 | -1 |
| `SALE_MOVEMENT` | -1 | -1 |
| `BIRTH_ISSUANCE` | +1 | +1 |
| `BIRTH_MOVEMENT` | +1 | +1 |
| `DEATH_ISSUANCE` | -1 | -1 |
| `DEATH_MOVEMENT` | -1 | -1 |
| `CONSUMPTION_ISSUANCE` | -1 | -1 |
| `CONSUMPTION_MOVEMENT` | -1 | -1 |
| `PURCHASE_ADJUSTMENT_INCREASE` | 0 or -qty | +1 (always positive) |
| `PURCHASE_ADJUSTMENT_DECREASE` | 0 or -qty | -1 (always negative) |
| `SALE_ADJUSTMENT_INCREASE` | 0 or +qty | +1 (always positive) |
| `SALE_ADJUSTMENT_DECREASE` | 0 or +qty | -1 (always negative) |
| `CAPITAL_GAIN` | 0 | +1 |
| `CAPITAL_LOSS` | 0 | -1 |

---

## 3. Idempotency Key Formats

### Current formats

| Method | Forward key | Reversal key |
|--------|------------|-------------|
| `record()` | `item_{item.pk}_product_{product.pk}` | `rev_item_{item.pk}_product_{product.pk}` |
| `record_movement_line()` | `movement_line_{line.pk}_product_{product.pk}` | `rev_movement_line_{line.reversal_of_id}_product_{product.pk}` |
| `record_adjustment_line()` | `adj_line_{line.pk}_product_{product.pk}` | `rev_adj_line_{line.pk}_product_{product.pk}` |

### New formats

| Method | Forward key | Reversal key |
|--------|------------|-------------|
| `record()` — issuance | `issuance_item_{item.pk}` | `rev_issuance_item_{item.pk}` |
| `record_movement_line()` | `movement_line_{line.pk}_product_{product.pk}` | `rev_movement_line_{line.reversal_of_id}_product_{product.pk}` |
| `record_adjustment_line()` — increase | `adj_inc_line_{line.pk}` | `rev_adj_line_{line.pk}` |
| `record_adjustment_line()` — decrease | `adj_dec_line_{line.pk}` | `rev_adj_line_{line.pk}` |

**Note:** Issuance and adjustment keys no longer include `product_{pk}` since entries may not have a product. This also means **one issuance entry per InvoiceItem** rather than one per Product-per-InvoiceItem.

---

## 4. Write Method Changes

### 4a. `record()` — Now writes issuance entries (product=NULL)

```python
@classmethod
def record(cls, operation, negate: bool = False, product_map: dict | None = None) -> tuple[int, int]:
    """
    Write issuance (or value-only) ledger entries for *operation*.

    *product_map*: ``{item_pk: [product, ...]}`` — for operations where
    products are known at issuance time (DEATH, CONSUMPTION).
    When absent (PURCHASE, SALE, BIRTH), issuance entries have ``product=None``.

    CAPITAL_GAIN/LOSS always use products from ``item.products.all()``.
    """
    _MAP = {
        OperationType.PURCHASE: (cls.EntryType.PURCHASE_ISSUANCE, 1, 1),
        OperationType.SALE: (cls.EntryType.SALE_ISSUANCE, -1, -1),
        OperationType.BIRTH: (cls.EntryType.BIRTH_ISSUANCE, 1, 1),
        OperationType.DEATH: (cls.EntryType.DEATH_ISSUANCE, -1, -1),
        OperationType.CONSUMPTION: (cls.EntryType.CONSUMPTION_ISSUANCE, -1, -1),
        OperationType.CAPITAL_GAIN: (cls.EntryType.CAPITAL_GAIN, 0, 1),
        OperationType.CAPITAL_LOSS: (cls.EntryType.CAPITAL_LOSS, 0, -1),
    }
    mapping = _MAP.get(operation.operation_type)
    if mapping is None:
        return 0, 0
    entry_type, qty_sign, val_sign = mapping

    if negate:
        qty_sign = -qty_sign
        val_sign = -val_sign
        entry_type = cls.EntryType.REVERSAL

    key_prefix = "rev_" if negate else ""
    date = operation.date
    created_count = skipped_count = 0

    for item in operation.items.all():
        # Determine which products to link (if any)
        if entry_type in (cls.EntryType.CAPITAL_GAIN, cls.EntryType.CAPITAL_LOSS):
            products = list(item.products.all())  # must exist
        elif product_map and item.pk in product_map:
            products = product_map[item.pk]        # known at issuance (DEATH, CONSUMPTION)
        else:
            products = [None]                      # lazy creation (PURCHASE, SALE, BIRTH)

        for product in products:
            if entry_type in (cls.EntryType.CAPITAL_GAIN, cls.EntryType.CAPITAL_LOSS):
                key = f"{key_prefix}item_{item.pk}_product_{product.pk}"
            else:
                key = f"{key_prefix}issuance_item_{item.pk}"

            defaults = {
                "product": product,
                "invoice_item": item,
                "entry_type": entry_type,
                "date": date,
                "quantity_delta": (item.quantity * qty_sign).quantize(Decimal("0.01")),
                "value_delta": (item.total_price * val_sign).quantize(Decimal("0.01")),
            }
            obj, created = cls.objects.get_or_create(
                idempotency_key=key, defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                skipped_count += 1

    return created_count, skipped_count
```

**Key changes:**
- `product_map` parameter added — allows DEATH/CONSUMPTION to link issuance to known products
- `CONSUMPTION_ISSUANCE` added to the MAP with `(-1, -1)` sign
- PURCHASE/SALE/BIRTH: `product=None` (lazy creation)
- DEATH/CONSUMPTION: `product=<selected product>` via `product_map`
- CAPITAL_GAIN/LOSS: unchanged (products from item.products.all())
- Idempotency key: `issuance_item_{item.pk}` for all issuance entries

### 4b. `record_movement_line()` — Now writes movement-type entries

```python
@classmethod
def record_movement_line(cls, line, negate: bool = False) -> tuple[int, int]:
    _MAP = {
        OperationType.PURCHASE: (cls.EntryType.PURCHASE_MOVEMENT, 1, 1),
        OperationType.SALE: (cls.EntryType.SALE_MOVEMENT, -1, -1),
        OperationType.BIRTH: (cls.EntryType.BIRTH_MOVEMENT, 1, 1),
        OperationType.DEATH: (cls.EntryType.DEATH_MOVEMENT, -1, -1),
        OperationType.CONSUMPTION: (cls.EntryType.CONSUMPTION_MOVEMENT, -1, -1),
        OperationType.CAPITAL_GAIN: (cls.EntryType.CAPITAL_GAIN, 0, 1),
        OperationType.CAPITAL_LOSS: (cls.EntryType.CAPITAL_LOSS, 0, -1),
    }
    mapping = _MAP.get(line.operation.operation_type)
    if mapping is None:
        return 0, 0

    entry_type, qty_sign, val_sign = mapping
    if negate:
        qty_sign = -qty_sign
        val_sign = -val_sign
        entry_type = cls.EntryType.REVERSAL

    product = line.product
    if product is None:
        return 0, 0  # safety guard — product must exist at movement time

    source_pk = line.reversal_of_id if negate else line.pk
    key_prefix = "rev_" if negate else ""
    key = f"{key_prefix}movement_line_{source_pk}_product_{product.pk}"

    item = line.invoice_item
    obj, created = cls.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "product": product,
            "invoice_item": item,
            "entry_type": entry_type,
            "date": line.date,
            "quantity_delta": (line.quantity * qty_sign).quantize(Decimal("0.01")),
            "value_delta": (line.quantity * item.unit_price * val_sign).quantize(
                Decimal("0.01")
            ),
        },
    )
    return (1, 0) if created else (0, 1)
```

**Key changes:**
- Entry types now use `_MOVEMENT` variants (PURCHASE_MOVEMENT, SALE_MOVEMENT, etc.)
- Added `invoice_item=item` to every entry
- CAPITAL_GAIN/LOSS stay as-is in the MAP (value-only, no movement)

### 4c. `record_adjustment_line()` — Now uses adjustment-specific types with hardcoded direction

Following the `TransactionType` pattern, direction is encoded in the type name:

- `PURCHASE_ADJ_INC` → always positive (contract value increased)
- `PURCHASE_ADJ_DEC` → always negative (contract value decreased)
- `SALE_ADJ_INC` → always positive
- `SALE_ADJ_DEC` → always negative

```python
_ADJUSTMENT_TYPE_MAP = {
    (OperationType.PURCHASE, True):  cls.EntryType.PURCHASE_ADJUSTMENT_INCREASE,
    (OperationType.PURCHASE, False): cls.EntryType.PURCHASE_ADJUSTMENT_DECREASE,
    (OperationType.SALE, True):      cls.EntryType.SALE_ADJUSTMENT_INCREASE,
    (OperationType.SALE, False):     cls.EntryType.SALE_ADJUSTMENT_DECREASE,
}

@classmethod
def record_adjustment_line(cls, line, negate: bool = False) -> tuple[int, int]:
    val_delta = line.value_delta
    qty_delta = line.quantity_delta

    if val_delta == 0 and qty_delta == 0:
        return 0, 0

    op_type = line.adjustment.operation.operation_type

    # Direction: is the contract value increasing or decreasing?
    is_increase = val_delta > 0 or (val_delta == 0 and qty_delta > 0)

    try:
        entry_type = cls._ADJUSTMENT_TYPE_MAP[(op_type, is_increase)]
    except KeyError:
        return 0, 0

    key = f"rev_adj_{'inc' if is_increase else 'dec'}_line_{line.pk}" if negate \
          else f"adj_{'inc' if is_increase else 'dec'}_line_{line.pk}"

    if negate:
        val_delta = -val_delta
        qty_delta = -qty_delta

    obj, created = cls.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "product": None,
            "invoice_item": line.invoice_item,
            "entry_type": entry_type,
            "date": line.adjustment.date,
            "quantity_delta": qty_delta.quantize(Decimal("0.01")),
            "value_delta": val_delta.quantize(Decimal("0.01")),
        },
    )
    return (1, 0) if created else (0, 1)
```

**Key changes:**
- Uses adjustment-specific types (`PURCHASE_ADJ_INC`, `PURCHASE_ADJ_DEC`, etc.) — not generic `ADJUSTMENT` or reused issuance types
- Direction hardcoded in type name — no runtime `val_sign` computation
- `quantity_delta` and `value_delta` stored as-is (the type name encodes the sign)
- On reversal (`negate=True`), type **stays the same** (INC stays INC, DEC stays DEC) — only the deltas are negated. Both INC and DEC are included in `_ISSUANCE_TYPES_FOR_PURCHASE` so they cancel naturally: a DEC with -100 reversed by a DEC with +100 = net 0.
- `product=None`, `invoice_item=line.invoice_item`
- Idempotency key: `adj_inc_line_{pk}` / `adj_dec_line_{pk}` (forward), `rev_adj_inc_line_{pk}` / `rev_adj_dec_line_{pk}` (reversal)

**Impact on existing tests:**
Tests asserting `entry_type == ADJUSTMENT` will fail — assert `PURCHASE_ADJ_DEC` instead.
Tests asserting `quantity_delta == 0` for quantity adjustments will also fail.

---

## 5. `save_inventory()` — Write Issuance Entries

### Current behavior

| Operation Type | Current |
|---------------|---------|
| PURCHASE | No-op |
| SALE | No-op |
| BIRTH | Auto-create movement lines |
| DEATH | Auto-create movement lines |
| CAPITAL_GAIN/LOSS | Link products + `record()` |

### New behavior

```python
def save_inventory(self, bound_formset):
    from apps.app_inventory.models import ProductLedgerEntry

    if self.operation_type in (
        OperationType.PURCHASE,
        OperationType.SALE,
        OperationType.BIRTH,
    ):
        # Issuance with product=None (lazy creation)
        ProductLedgerEntry.record(self)

    elif self.operation_type in (OperationType.DEATH, OperationType.CONSUMPTION):
        # Build product_map from formset — products ARE selected
        product_map = {}
        for form in bound_formset.forms:
            item = form.instance
            if not item.pk:
                continue
            selected = form.cleaned_data.get("selected_product")
            if selected:
                product_map[item.pk] = [selected]
        ProductLedgerEntry.record(self, product_map=product_map)

    # Auto-create movement lines for BIRTH, DEATH, CONSUMPTION
    if self.operation_type in (
        OperationType.BIRTH,
        OperationType.DEATH,
        OperationType.CONSUMPTION,
    ):
        self._auto_create_inventory_movements(bound_formset)

    elif self.operation_type in (
        OperationType.CAPITAL_GAIN,
        OperationType.CAPITAL_LOSS,
    ):
        # Link products + record (unchanged)
        for form in bound_formset.forms:
            item = form.instance
            if not item.pk:
                continue
            selected = form.cleaned_data.get("selected_product")
            if selected:
                is_reversal = getattr(self, "reversal_of_id", None) is not None
                selected.validate_active(allow_reversal=is_reversal)
                selected.invoice_items.add(item)
        ProductLedgerEntry.record(self)

    # PURCHASE/SALE: issuance written above, movements are user-driven later
```

**Key changes:**
- ALL invoiced operations now write issuance entries (consistency, no branches)
- PURCHASE/SALE/BIRTH: `product=None` (lazy creation)
- DEATH/CONSUMPTION: `product=<selected product>` via `product_map`
- BIRTH/DEATH/CONSUMPTION: issuance + auto-movement lines
- PURCHASE/SALE: issuance only (user creates movements later)

---

## 6. Query Method Changes

### 6a. `state_as_of(product, as_of)` — Filter by movement types only

```python
MOVEMENT_TYPES = [
    cls.EntryType.PURCHASE_MOVEMENT,
    cls.EntryType.SALE_MOVEMENT,
    cls.EntryType.BIRTH_MOVEMENT,
    cls.EntryType.DEATH_MOVEMENT,
    cls.EntryType.CONSUMPTION_MOVEMENT,
    cls.EntryType.CAPITAL_GAIN,
    cls.EntryType.CAPITAL_LOSS,
]

@classmethod
def state_as_of(cls, product, as_of) -> dict:
    result = cls.objects.filter(
        product=product,
        date__lte=as_of,
        entry_type__in=cls.MOVEMENT_TYPES + [cls.EntryType.REVERSAL],
    ).aggregate(
        quantity=Sum("quantity_delta"),
        value=Sum("value_delta"),
    )
    return {
        "quantity": result["quantity"] or Decimal("0.00"),
        "value": result["value"] or Decimal("0.00"),
    }
```

**Why filter?** Issuance entries have `product=None` so they won't match `product=product` anyway. But for safety and clarity, we restrict to movement types. CAPITAL_GAIN/LOSS are included since they affect value.

### 6b. `portfolio_as_of(entity, as_of)` — Filter by movement types

```python
@classmethod
def portfolio_as_of(cls, entity, as_of):
    return (
        cls.objects.filter(
            product__product_template__entities=entity,
            date__lte=as_of,
            entry_type__in=cls.MOVEMENT_TYPES + [cls.EntryType.REVERSAL],
        )
        .values("product_id")
        .annotate(
            quantity=Sum("quantity_delta"),
            value=Sum("value_delta"),
        )
        .filter(quantity__gt=0)
        .order_by("product_id")
    )
```

### 6c. `inventory_value_at(entity, as_of)` — Unchanged (SUM already works)

```python
@classmethod
def inventory_value_at(cls, entity, as_of) -> Decimal:
    result = cls.objects.filter(
        product__product_template__entities=entity,
        date__lte=as_of,
        entry_type__in=cls.MOVEMENT_TYPES + [cls.EntryType.REVERSAL],
    ).aggregate(value=Sum("value_delta"))
    return result["value"] or Decimal("0.00")
```

### 6d. `pending_deliveries(entity, as_of)` — Rewritten using issuance - movement

This is the KEY method that solves the partial-delivery problem.

The issuance total must include **all** entry types that represent contract obligations:
- `PURCHASE_ISSUANCE` — original contract amount
- `PURCHASE_ADJ_INC` — contract increases
- `PURCHASE_ADJ_DEC` — contract decreases (negative)

```python
_ISSUANCE_TYPES_FOR_PURCHASE = [
    cls.EntryType.PURCHASE_ISSUANCE,
    cls.EntryType.PURCHASE_ADJUSTMENT_INCREASE,
    cls.EntryType.PURCHASE_ADJUSTMENT_DECREASE,
]

_MOVEMENT_TYPES_FOR_PURCHASE = [
    cls.EntryType.PURCHASE_MOVEMENT,
]

@classmethod
def pending_deliveries(cls, entity=None, as_of=None):
    """
    Return InvoiceItems where issuance > movement (under-delivered).

    Pending = SUM(issuance_delta) - SUM(movement_delta)

    Issuance includes: PURCHASE_ISSUANCE + PURCHASE_ADJ_INC + PURCHASE_ADJ_DEC
    Movement includes: PURCHASE_MOVEMENT
    """
    from django.db.models import OuterRef, Subquery, Sum, Value
    from django.db.models.functions import Coalesce

    qs = InvoiceItem.objects.all()

    issuance_qty = Coalesce(
        Subquery(
            cls.objects.filter(
                invoice_item=OuterRef("pk"),
                entry_type__in=cls._ISSUANCE_TYPES_FOR_PURCHASE,
            )
            .values("invoice_item")
            .annotate(total=Sum("quantity_delta"))
            .values("total"),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
        Value(Decimal("0.00")),
    )

    movement_qty = Coalesce(
        Subquery(
            cls.objects.filter(
                invoice_item=OuterRef("pk"),
                entry_type__in=cls._MOVEMENT_TYPES_FOR_PURCHASE,
            )
            .exclude(entry_type=cls.EntryType.REVERSAL)
            .values("invoice_item")
            .annotate(total=Sum("quantity_delta"))
            .values("total"),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
        Value(Decimal("0.00")),
    )

    qs = qs.annotate(
        issuance_qty=issuance_qty,
        movement_qty=movement_qty,
        pending_qty=ExpressionWrapper(
            F("issuance_qty") - F("movement_qty"),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
    ).filter(pending_qty__gt=0)

    if entity:
        qs = qs.filter(operation__entity=entity)
    if as_of:
        qs = qs.filter(operation__date__lte=as_of)

    return qs.values(
        "id",
        "quantity",
        "issuance_qty",
        "movement_qty",
        "pending_qty",
        "product_template__name",
        "operation__id",
    ).order_by("operation__date")
```

**This replaces both `unreceived_purchases()` and `undelivered_sales()`.**

### 6e. Remove `unreceived_purchases()` and `undelivered_sales()`

These classmethods on `InvoiceItem` are replaced by `ProductLedgerEntry.pending_deliveries()`. Delete them.

```python
# DELETE these methods:
# @classmethod
# def unreceived_purchases(cls): ...
# @classmethod
# def undelivered_sales(cls): ...
```

### 6f. Add `pending_sales(entity, as_of)` for SALE operations (if needed)

Similar to `pending_deliveries()` but for SALE operations:

```python
@classmethod
def pending_sales(cls, entity=None, as_of=None):
    """Return InvoiceItems where issuance > movement (under-delivered sales)."""
    # Same pattern as pending_deliveries but uses SALE_ISSUANCE / SALE_MOVEMENT
    # Note: SALE uses negative qty_sign, so pending = |issuance| - |movement|
    ...
```

Actually, since both PURCHASE and SALE use issuance - movement, we can handle both in one method. But the sign convention is different (SALE is negative), so we need absolute values.

Simpler approach: Use a single method `pending_items()` that takes an OperationType filter:

```python
@classmethod
def pending_items(cls, op_type, entity=None, as_of=None):
    """Generic pending calculator for any operation type with issuance/movement split."""
    issuance_type_map = {
        OperationType.PURCHASE: cls.EntryType.PURCHASE_ISSUANCE,
        OperationType.SALE: cls.EntryType.SALE_ISSUANCE,
        OperationType.BIRTH: cls.EntryType.BIRTH_ISSUANCE,
        OperationType.DEATH: cls.EntryType.DEATH_ISSUANCE,
    }
    movement_type_map = {
        OperationType.PURCHASE: cls.EntryType.PURCHASE_MOVEMENT,
        OperationType.SALE: cls.EntryType.SALE_MOVEMENT,
        OperationType.BIRTH: cls.EntryType.BIRTH_MOVEMENT,
        OperationType.DEATH: cls.EntryType.DEATH_MOVEMENT,
    }
    # ... query using issuance_type - movement_type, with ABS() for SALE/DEATH
```

---

## 7. `stock_detail()` View — Use Ledger for Pending Quantities

### Current (broken for partial deliveries)

```python
unreceived_purchases = InvoiceItem.unreceived_purchases()  # .exclude() — BROKEN
undelivered_sales = InvoiceItem.undelivered_sales()         # .exclude() — BROKEN
```

### New

```python
from apps.app_inventory.models import ProductLedgerEntry

# Pending inbound (Purchase + Birth obligations not yet moved)
pending_in = ProductLedgerEntry.pending_items(OperationType.PURCHASE, entity=entity)
pending_birth = ProductLedgerEntry.pending_items(OperationType.BIRTH, entity=entity)

# Pending outbound (Sale + Death obligations not yet moved)
pending_out = ProductLedgerEntry.pending_items(OperationType.SALE, entity=entity)
pending_death = ProductLedgerEntry.pending_items(OperationType.DEATH, entity=entity)

obligated_inbound_qty = sum(item["pending_qty"] for item in chain(pending_in, pending_birth))
obligated_outbound_qty = sum(item["pending_qty"] for item in chain(pending_out, pending_death))
```

---

## 8. Reversal Logic — `Operation.reverse()`

### Current

```python
if self.operation_type in (OperationType.PURCHASE, OperationType.SALE):
    moved = self.movement_lines.filter(reversal_of__isnull=True).exists()
    if moved:
        raise ValidationError(...)
elif self.operation_type in (OperationType.BIRTH, OperationType.DEATH):
    for line in self.movement_lines.filter(reversal_of__isnull=True):
        line.reverse(officer=officer, date=date)
elif self.operation_type in (OperationType.CAPITAL_GAIN, OperationType.CAPITAL_LOSS):
    ProductLedgerEntry.record(self, negate=True)
```

### New

```python
if self.operation_type in (OperationType.PURCHASE, OperationType.SALE):
    # Check for movements
    moved = self.movement_lines.filter(reversal_of__isnull=True).exists()
    if moved:
        raise ValidationError(
            _("Cannot reverse this operation. Reverse all inventory movements first.")
        )
    # Reverse issuance entries
    ProductLedgerEntry.record(self, negate=True)

elif self.operation_type in (OperationType.BIRTH, OperationType.DEATH, OperationType.CONSUMPTION):
    # Reverse issuance entries
    ProductLedgerEntry.record(self, negate=True)
    # Reverse movement lines
    for line in self.movement_lines.filter(reversal_of__isnull=True):
        line.reverse(officer=officer, date=date)

elif self.operation_type in (OperationType.CAPITAL_GAIN, OperationType.CAPITAL_LOSS):
    ProductLedgerEntry.record(self, negate=True)
```

**Key change:** PURCHASE/SALE reversal now negates issuance entries as well (since `save_inventory()` now writes them). Before, there were no issuance entries to reverse.

---

## 9. Adjustment Reversal — `InvoiceItemAdjustment.reverse()`

### Current

```python
for line in self.lines.all():
    ProductLedgerEntry.record_adjustment_line(line, negate=True)
```

### New

Same code — `record_adjustment_line()` now writes issuance-type entries with corrected deltas, so negate flips them. **No change needed** to the reversal logic, just the underlying method.

---

## 10. Data Migration

### Challenge

Existing entries use old type names (`PURCHASE`, `SALE`, `BIRTH`, `DEATH`, `CONSUMPTION`, `ADJUSTMENT`). We need to migrate them all to the new types. Since the project is in development, we can remove `ADJUSTMENT` from the enum entirely.

### Strategy

The `idempotency_key` format tells us which method created each entry:

| Key pattern | Created by | New type |
|------------|-----------|----------|
| `item_{pk}_product_{pk}` | `record()` | → `PURCHASE_ISSUANCE`, `SALE_ISSUANCE`, `BIRTH_ISSUANCE`, `DEATH_ISSUANCE` |
| `rev_item_{pk}_product_{pk}` | `record(negate=True)` | → `REVERSAL` (keep) |
| `movement_line_{pk}_product_{pk}` | `record_movement_line()` | → `PURCHASE_MOVEMENT`, `SALE_MOVEMENT`, etc. |
| `rev_movement_line_{pk}_product_{pk}` | `record_movement_line(negate=True)` | → `REVERSAL` (keep) |
| `adj_line_{pk}_product_{pk}` | `record_adjustment_line()` | → `PURCHASE_ADJ_DEC` or `SALE_ADJ_DEC` (old adjustments were always decreases) |

### Migration SQL (pseudocode)

```python
def migrate_entry_types(apps, schema_editor):
    PLE = apps.get_model("app_inventory", "ProductLedgerEntry")
    
    # 1. Entries from record() — key starts with "item_" or "rev_item_"
    for entry in PLE.objects.filter(
        entry_type__in=["PURCHASE", "SALE", "BIRTH", "DEATH", "CONSUMPTION"],
        idempotency_key__regex=r'^(rev_)?item_\d+_product_\d+$',
    ):
        type_map = {
            "PURCHASE": "PURCHASE_ISSUANCE",
            "SALE": "SALE_ISSUANCE",
            "BIRTH": "BIRTH_ISSUANCE",
            "DEATH": "DEATH_ISSUANCE",
            "CONSUMPTION": "CONSUMPTION_ISSUANCE",
        }
        entry.entry_type = type_map.get(entry.entry_type, entry.entry_type)
        entry.save(update_fields=["entry_type"])

    # 2. Entries from record_movement_line() — key starts with "movement_line_"
    for entry in PLE.objects.filter(
        entry_type__in=["PURCHASE", "SALE", "BIRTH", "DEATH", "CONSUMPTION"],
        idempotency_key__startswith=("movement_line_", "rev_movement_line_"),
    ):
        type_map = {
            "PURCHASE": "PURCHASE_MOVEMENT",
            "SALE": "SALE_MOVEMENT",
            "BIRTH": "BIRTH_MOVEMENT",
            "DEATH": "DEATH_MOVEMENT",
            "CONSUMPTION": "CONSUMPTION_MOVEMENT",
        }
        entry.entry_type = type_map.get(entry.entry_type, entry.entry_type)
        entry.save(update_fields=["entry_type"])

    # 3. ADJUSTMENT entries → adjustment-specific types
    # Old adjustments were always contract decreases, so map to _DEC types.
    # To determine Purchase vs Sale, join via invoice_item → operation.
    from django.db.models import OuterRef, Subquery

    op_type_subq = Subquery(
        InvoiceItem.objects.filter(
            pk=OuterRef("invoice_item_id")
        ).values("operation__operation_type")[:1]
    )

    PLE.objects.filter(entry_type="ADJUSTMENT").update(
        entry_type=Case(
            When(
                invoice_item__operation__operation_type="PURCHASE",
                then=Value("PURCHASE_ADJ_DEC"),
            ),
            When(
                invoice_item__operation__operation_type="SALE",
                then=Value("SALE_ADJ_DEC"),
            ),
            default=Value("PURCHASE_ADJ_DEC"),  # fallback
            output_field=CharField(),
        )
    )
```

### Key migration details

- `ADJUSTMENT` type is **removed** from the enum — all entries migrated
- Old ADJUSTMENT entries used `val_sign` computed at runtime; new types have direction hardcoded
- For backward safety, old ADJUSTMENT entries with positive value_delta are mapped to `_DEC` types
  (since the old code used `val_sign` to invert the sign, a positive stored value means "decrease")

### Migration: Nullable `product` and new `invoice_item`

New `product` field is nullable — existing entries keep their product FK. New `invoice_item` field is nullable — existing entries get `NULL` initially. A data migration can backfill `invoice_item` for existing entries where possible (by parsing the idempotency key to find the invoice_item).

```python
# Backfill invoice_item for entries where product is set
# Join through Product.invoice_items M2M
for entry in PLE.objects.filter(invoice_item__isnull=True, product__isnull=False):
    # A Product can have multiple invoice_items — take the first
    first_item = entry.product.invoice_items.first()
    if first_item:
        entry.invoice_item = first_item
        entry.save(update_fields=["invoice_item"])
```

---

## 11. Template Changes

### `stock_detail.html` — Pending sections

The obligated inbound/outbound sections currently show `unreceived_items` and `undelivered_items`. Under the new design, these use `pending_items()` results.

The template already has card sections for inbound/outbound obligations. The data source changes from `InvoiceItem.unreceived_purchases()` to `ProductLedgerEntry.pending_items()` but the display logic stays similar.

**Minimal template changes** — mainly updating context variable names and ensuring `pending_qty` is displayed instead of raw `item.quantity`.

---

## 12. Test Changes

### `test_invoice_item_adjustment_ledger_entry.py`

**Test: `test_purchase_price_decrease_ledger_entry`**
```python
# Current: asserts entry_type == ADJUSTMENT, quantity_delta == 0
# New: price-only decrease → PURCHASE_ADJ_DEC, value_delta stored as-is
self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.PURCHASE_ADJUSTMENT_DECREASE)
self.assertEqual(entry.quantity_delta, Decimal("0.00"))
self.assertEqual(entry.value_delta, Decimal("-100.00"))
```

**Test: `test_purchase_quantity_decrease_ledger_entry`**
```python
# Current: asserts quantity_delta == -2.00 (was writing qty delta to ADJUSTMENT with quantity_delta=0 bug)
# New: adjustment stores quantity_delta as-is (no sign multiplication)
# The type name (PURCHASE_ADJ_DEC) encodes the direction — DEC = always negative effect
self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.PURCHASE_ADJUSTMENT_DECREASE)
self.assertEqual(entry.quantity_delta, Decimal("-2.00"))
self.assertEqual(entry.value_delta, Decimal("-200.00"))
```

**Test: `test_sale_price_decrease_ledger_entry`**
```python
# Current: asserts entry_type == ADJUSTMENT
# New: SALE price decrease → SALE_ADJ_DEC
self.assertEqual(entry.entry_type, ProductLedgerEntry.EntryType.SALE_ADJUSTMENT_DECREASE)
```

**Test: `test_idempotency_key_prevents_duplicate_entries`**
```python
# Current: checks for ADJUSTMENT entry
# New: checks for specific adjustment type
self.assertEqual(
    entry.idempotency_key,
    "adj_dec_line_1",  # format: adj_{inc|dec}_line_{line.pk}
)
```

### `test_invoice_item_adjustment_validation.py` — Test `test_ledger_entry_still_recorded_after_movement`

This test likely creates a movement and then checks that adjustment ledger entries are still created. The `record_adjustment_line()` now writes issuance type instead of ADJUSTMENT. Update the assertion.

---

## 13. Design Decisions Summary

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | `product` nullable for issuance entries | Products don't exist at contract time |
| 2 | `invoice_item` FK on ALL entries | Enables `SUM(issuance WHERE invoice_item=X)` for pending calculation |
| 3 | One issuance entry per InvoiceItem, not per product | Products don't exist yet; contract is at InvoiceItem level |
| 4 | Movement entries also store `invoice_item` | Consistent with issuance; enables JOIN-based queries |
| 5 | `ADJUSTMENT` **removed** from enum | Project is in development — migrate all entries to `PURCHASE_ADJ_DEC` / `SALE_ADJ_DEC` |
| 6 | Sign conventions match existing `_MAP` | Consistency — issuance and movement use same signs |
| 7 | `pending_deliveries()` uses Ledger instead of MovementLine | Allows querying pending BEFORE any movement lines exist |
| 8 | Remove `unreceived_purchases()` / `undelivered_sales()` | Replaced by `pending_items()` which works with partial deliveries |

---

## 14. Migration Safety — Rollback Plan

If the migration fails:
1. `product` and `invoice_item` are nullable — no data loss
2. Old entry types remain readable (we only UPDATE the `entry_type` string)
3. The `REVERSAL` entry type is unchanged
4. Old `ADJUSTMENT` entries are migrated to `PURCHASE_ADJ_DEC` / `SALE_ADJ_DEC` — data is preserved, just renamed

Rollback: Re-run migration with old type names. The idempotency keys haven't changed format, so new entries would have different keys (no collisions).

---

## 15. Summary of All Code Changes

### `models.py` (ProductLedgerEntry)
- [ ] Make `product` nullable (null=True, blank=True)
- [ ] Add `invoice_item` FK to InvoiceItem (nullable)
- [ ] Extend `entry_type` max_length from 20 to 30
- [ ] Add `MOVEMENT_TYPES` class constant
- [ ] Rewrite EntryType enum with issuance/movement split
- [ ] Rewrite `record()` — writes issuance entries with product=None
- [ ] Rewrite `record_movement_line()` — writes _MOVEMENT types
- [ ] Rewrite `record_adjustment_line()` — writes issuance correction
- [ ] Rewrite `state_as_of()` — filter by movement types
- [ ] Rewrite `portfolio_as_of()` — filter by movement types
- [ ] Rewrite `inventory_value_at()` — filter by movement types
- [ ] Rewrite `pending_deliveries()` — use issuance - movement from ledger
- [ ] Add `pending_items()` — generic pending calculator
- [ ] Remove `InvoiceItem.unreceived_purchases()` and `undelivered_sales()`

### `operation.py`
- [ ] `save_inventory()` — write issuance entries for PURCHASE/SALE/BIRTH/DEATH/CONSUMPTION
- [ ] `reverse()` — reverse issuance entries for PURCHASE/SALE/BIRTH/DEATH/CONSUMPTION

### `views.py` (stock_detail)
- [ ] Replace `unreceived_purchases()` / `undelivered_sales()` calls with `pending_items()`
- [ ] Update context variables

### `adjustment/models.py`
- [ ] `record_adjustment_line()` writes adjustment-specific types (PURCHASE_ADJ_INC / PURCHASE_ADJ_DEC / SALE_ADJ_INC / SALE_ADJ_DEC)
- [ ] Change idempotency key format from `adj_line_{pk}_product_{pk}` to `adj_{inc|dec}_line_{pk}`
- [ ] Remove `ADJUSTMENT` from EntryType enum

### Migration
- [ ] Add data migration for entry_type values
- [ ] Backfill invoice_item where possible

### Tests
- [ ] Update `test_invoice_item_adjustment_ledger_entry.py` assertions
- [ ] Update `test_invoice_item_adjustment_validation.py` assertions
- [ ] Add tests for `pending_items()` with partial deliveries
