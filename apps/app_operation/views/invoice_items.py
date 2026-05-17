from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.shortcuts import render

from apps.app_adjustment.models import InvoiceItemAdjustment, InvoiceItemAdjustmentLine
from apps.app_base.debug import DebugContext, debug_view
from apps.app_operation.models import Operation
from farm.shortcuts import get_object_or_404


@debug_view
def invoice_items_list_view(request, pk):
    """Display all invoice items for an operation in a dedicated list view.

    Each invoice item is rendered as its own card showing:
    - Item details (product, description)
    - Price info (unit price, total, adjusted values)
    - Item adjustments (adjustment lines affecting this item)
    - Inventory movement status
    """
    with DebugContext.section(
        "Fetching operation for invoice items list",
        {
            "operation_pk": pk,
            "user": request.user.username,
        },
    ):
        operation = get_object_or_404(
            Operation, pk=pk, error_message="Operation not found or has been deleted."
        )
        operation = Operation.objects.cast(operation)
        DebugContext.success(
            "Operation loaded",
            {
                "operation_id": operation.pk,
                "operation_type": operation.operation_type,
                "has_invoice": type(operation).has_invoice,
            },
        )

    with DebugContext.section(
        "Fetching invoice items, adjustments, and movement data",
        {
            "operation_id": operation.pk,
            "has_invoice": type(operation).has_invoice,
        },
    ):
        items = operation.items.all() if type(operation).has_invoice else []
        DebugContext.log(
            "Invoice items fetched",
            {
                "count": len(items),
                "operation_id": operation.pk,
            },
        )

        # Prefetch item-adjustment lines per invoice item
        item_adjustments = (
            InvoiceItemAdjustmentLine.objects.filter(
                invoice_item__operation=operation,
                adjustment__reversed_by__isnull=True,
            )
            .select_related("adjustment", "adjustment__officer")
            .order_by("-adjustment__date", "-adjustment__pk")
        )
        DebugContext.log(
            "Item adjustment lines fetched",
            {
                "count": len(item_adjustments),
                "operation_id": operation.pk,
            },
        )

        # Group adjustment lines by invoice_item_id for quick lookup
        adj_lines_by_item: dict[int, list[InvoiceItemAdjustmentLine]] = defaultdict(
            list
        )
        for line in item_adjustments:
            adj_lines_by_item[line.invoice_item_id].append(line)
        DebugContext.log(
            "Adjustment lines grouped by invoice item",
            {
                "items_with_adj": len(adj_lines_by_item),
                "operation_id": operation.pk,
            },
        )

        # Fetch item adjustments (for reversed/original info per adjustment group)
        item_adjustments_grouped = (
            InvoiceItemAdjustment.objects.filter(
                operation=operation,
            )
            .select_related("officer", "adjustment")
            .order_by("-date", "-pk")
        )
        DebugContext.log(
            "Item adjustments (grouped) fetched",
            {
                "count": len(item_adjustments_grouped),
                "operation_id": operation.pk,
            },
        )

        items_data = operation.get_items_data()
        DebugContext.log(
            "Items movement data computed",
            {
                "items_count": len(items_data),
                "operation_id": operation.pk,
            },
        )

    # Build a lookup from items_data by item pk
    items_data_by_pk = {entry["item"].pk: entry for entry in items_data}

    # Merge items with their adjustment lines and movement data
    merged_items = []
    for item in items:
        merged_items.append(
            {
                "item": item,
                "adjustment_lines": adj_lines_by_item.get(item.pk, []),
                "movement_data": items_data_by_pk.get(item.pk),
            }
        )

    # Compute total from items' adjusted prices (sum of adjusted_total_price)
    total_adjusted = sum(
        (item.adjusted_total_price for item in items),
        Decimal("0.00"),
    )

    context = {
        "operation": operation,
        "merged_items": merged_items,
        "items_data": items_data,
        "item_adjustments": item_adjustments_grouped,
        "has_invoice": type(operation).has_invoice,
        "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
        "total_adjusted": total_adjusted,
    }
    return render(request, "app_operation/invoice_items_list.html", context)
