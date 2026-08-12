"""Stock queries — the single source of truth for "what's available" and
"inbound / outbound".

These are computed directly from ``InventoryMovementLine`` (the physical events)
plus ``InvoiceItem`` (contract obligations and capital value), with **no
separate ledger table**. This replaces the old ``ProductLedgerEntry`` queries.
"""
from datetime import date as _today
from decimal import Decimal

from apps.app_operation.models.operation_type import OperationType

_INBOUND_TYPES = (OperationType.PURCHASE, OperationType.BIRTH)
_OUTBOUND_TYPES = (OperationType.DEATH, OperationType.CONSUMPTION)

# Issued-quantity sign per operation type (for pending/obligation maths).
_ISSUE_SIGN = {
    OperationType.PURCHASE: Decimal("1"),
    OperationType.BIRTH: Decimal("1"),
    OperationType.SALE: Decimal("-1"),
    OperationType.DEATH: Decimal("-1"),
    OperationType.CONSUMPTION: Decimal("-1"),
}


def valuation_unit_cost(product) -> Decimal:
    """The carried unit cost used to value movements (purchase-price basis)."""
    return product.unit_price or Decimal("0.00")


def active_movements(product, as_of=None):
    """Movement lines still physically active: not a reversal line, and not the
    original of a reversal line (i.e. not reversed). Optionally up to *as_of*."""
    from apps.app_inventory.models import InventoryMovementLine

    reversed_originals = InventoryMovementLine.objects.filter(
        product=product, reversal_of__isnull=False
    ).values_list("reversal_of_id", flat=True)
    qs = (
        InventoryMovementLine.objects.filter(
            product=product, reversal_of__isnull=True
        )
        .exclude(id__in=list(reversed_originals))
        .select_related("operation")
    )
    if as_of is not None:
        qs = qs.filter(date__lte=as_of)
    return list(qs.order_by("date", "created_at"))


def active_lines_for_item(item):
    """Movement lines still physically active for an invoice item: not a
    reversal line, and not the original of a reversal line (i.e. not
    reversed). Mirrors ``active_movements()`` but keyed on the invoice item."""
    from apps.app_inventory.models import InventoryMovementLine

    reversed_originals = InventoryMovementLine.objects.filter(
        invoice_item=item, reversal_of__isnull=False
    ).values_list("reversal_of_id", flat=True)
    return (
        InventoryMovementLine.objects.filter(
            invoice_item=item, reversal_of__isnull=True
        )
        .exclude(id__in=list(reversed_originals))
        .select_related("operation")
    )


def movement_delta(line, product_entity_id) -> Decimal:
    """Direction-aware signed quantity of one movement line (mirrors the
    movement recording and the stock-detail classification).

    - PURCHASE/BIRTH → inbound (+)
    - DEATH/CONSUMPTION → outbound (−)
    - SALE → + for a buyer receipt (product owned by the SALE source), − for a
      seller dispatch
    """
    op_type = line.operation.operation_type
    if op_type in _INBOUND_TYPES:
        return line.quantity
    if op_type in _OUTBOUND_TYPES:
        return -line.quantity
    if op_type == OperationType.SALE:
        if product_entity_id == line.operation.source_id:
            return line.quantity
        return -line.quantity
    return Decimal("0")


def capital_delta(product) -> Decimal:
    """Value-only capital gain/loss from the linked capital operations that are
    still active (not reversed — a reversed capital op cancels its effect)."""
    total = Decimal("0")
    items = product.invoice_items.filter(
        operation__operation_type__in=(
            OperationType.CAPITAL_GAIN,
            OperationType.CAPITAL_LOSS,
        ),
        operation__reversed_by__isnull=True,
    ).select_related("operation")
    for item in items:
        sign = (
            Decimal("1")
            if item.operation.operation_type == OperationType.CAPITAL_GAIN
            else Decimal("-1")
        )
        total += sign * (item.quantity * item.unit_price)
    return total


def movement_state(product, as_of=None) -> dict:
    """``{"quantity", "value"}`` physically present for *product* as of
    *as_of*. Quantity is the net direction-aware movement; value is that
    quantity at the carried cost plus any capital gain/loss."""
    lines = active_movements(product, as_of=as_of)
    qty = sum(
        (movement_delta(line, product.entity_id) for line in lines), Decimal("0")
    )
    value = qty * valuation_unit_cost(product) + capital_delta(product)
    return {"quantity": qty, "value": value}


def portfolio(entity, as_of=None):
    """Per-product physical presence for *entity* — a list of dicts with
    ``product_id``, ``quantity`` (> 0) and ``value``."""
    from apps.app_inventory.models import Product

    as_of = as_of or _today.today()
    rows = []
    for product in Product.objects.filter(entity=entity).iterator():
        state = movement_state(product, as_of)
        if state["quantity"] > 0:
            rows.append(
                {
                    "product_id": product.pk,
                    "quantity": state["quantity"],
                    "value": state["value"],
                }
            )
    return rows


def inventory_value(entity, as_of=None) -> Decimal:
    """Net book value of inventory for *entity* as of *as_of* (movement value +
    capital, summed across the entity's owned products)."""
    from apps.app_inventory.models import Product

    as_of = as_of or _today.today()
    total = Decimal("0")
    for product in Product.objects.filter(entity=entity).iterator():
        total += movement_state(product, as_of)["value"]
    return total


def _item_moved_qty(item, as_of=None) -> Decimal:
    """Direction-aware moved quantity for an invoice item (net of reversals)."""
    from apps.app_inventory.models import InventoryMovementLine

    reversed_originals = InventoryMovementLine.objects.filter(
        invoice_item=item, reversal_of__isnull=False
    ).values_list("reversal_of_id", flat=True)
    qs = (
        InventoryMovementLine.objects.filter(
            invoice_item=item, reversal_of__isnull=True
        )
        .exclude(id__in=list(reversed_originals))
        .select_related("operation")
    )
    if as_of is not None:
        qs = qs.filter(date__lte=as_of)
    total = Decimal("0")
    for line in qs.iterator():
        entity_id = line.product.entity_id if line.product_id else None
        total += movement_delta(line, entity_id)
    return total


def pending_items(entity=None, as_of=None):
    """InvoiceItems where the moved quantity differs from the issued
    (contracted) quantity. Positive = inbound pending (purchase/birth),
    negative = outbound pending (sale/death/consumption).

    Returns a list of dicts with ``id``, ``quantity``, ``issued_qty``,
    ``moved_qty``, ``pending_qty``, ``product_template__name``,
    ``operation__id``, ``operation__date``.
    """
    from django.db.models import Q

    from apps.app_inventory.models import InvoiceItem

    qs = InvoiceItem.objects.filter(
        operation__operation_type__in=_ISSUE_SIGN.keys()
    ).select_related("operation", "product_template")
    if entity:
        qs = qs.filter(
            Q(operation__source=entity) | Q(operation__destination=entity)
        )
    if as_of:
        qs = qs.filter(operation__date__lte=as_of)

    rows = []
    for item in qs.iterator():
        issued = item.quantity * _ISSUE_SIGN[item.operation.operation_type]
        moved = _item_moved_qty(item, as_of)
        pending = issued - moved
        if pending != 0:
            rows.append(
                {
                    "id": item.pk,
                    "quantity": item.quantity,
                    "issued_qty": issued,
                    "moved_qty": moved,
                    "pending_qty": pending,
                    "product_template__name": item.product_template.name,
                    "operation__id": item.operation_id,
                    "operation__date": item.operation.date,
                    "operation__operation_type": item.operation.operation_type,
                }
            )
    rows.sort(key=lambda r: r["operation__date"])
    return rows


def pending_deliveries(entity=None, as_of=None):
    """Alias for ``pending_items()`` — items with pending inbound obligations."""
    return [
        row for row in pending_items(entity=entity, as_of=as_of)
        if row["pending_qty"] > 0
    ]
