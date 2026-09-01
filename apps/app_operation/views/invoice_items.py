from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.shortcuts import render
from django.views import View

from apps.app_adjustment.models import InvoiceItemAdjustment, InvoiceItemAdjustmentLine
from apps.app_base.logging_utils import logger
from apps.app_operation.models import Operation
from farm.shortcuts import get_object_or_404


class InvoiceItemsListView(View):
    """Display all invoice items for an operation in a dedicated list view.

    Each invoice item is rendered as its own card showing:
    - Item details (product, description)
    - Price info (unit price, total, adjusted values)
    - Item adjustments (adjustment lines affecting this item)
    - Inventory movement status
    """

    def get(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        logger.debug(
            f"Fetching operation for invoice items list | operation_pk={pk} | "
            f"user={request.user.username}"
        )
        operation = get_object_or_404(
            Operation, pk=pk, error_message="Operation not found or has been deleted."
        )
        operation = Operation.objects.cast(operation)
        logger.debug(
            f"Operation loaded | operation_id={operation.pk} | "
            f"operation_type={operation.operation_type} | "
            f"has_invoice={type(operation).has_invoice}"
        )

        logger.debug(
            f"Fetching invoice items, adjustments, and movement data | "
            f"operation_id={operation.pk} | has_invoice={type(operation).has_invoice}"
        )
        items = operation.items.all() if type(operation).has_invoice else []
        logger.debug(
            f"Invoice items fetched | count={len(items)} | operation_id={operation.pk}"
        )

        capital_valuations = []
        if type(operation).has_capital_valuation:
            capital_valuations = operation.capital_valuations.select_related(
                "product", "product__product_template", "officer"
            )
            logger.debug(
                f"Capital valuations fetched | count={len(capital_valuations)} | "
                f"operation_id={operation.pk}"
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
        logger.debug(
            f"Item adjustment lines fetched | count={len(item_adjustments)} | "
            f"operation_id={operation.pk}"
        )

        # Group adjustment lines by invoice_item_id for quick lookup
        adj_lines_by_item: dict[int, list[InvoiceItemAdjustmentLine]] = defaultdict(
            list
        )
        for line in item_adjustments:
            adj_lines_by_item[line.invoice_item_id].append(line)
        logger.debug(
            f"Adjustment lines grouped by invoice item | "
            f"items_with_adj={len(adj_lines_by_item)} | operation_id={operation.pk}"
        )

        # Fetch item adjustments (for reversed/original info per adjustment group)
        item_adjustments_grouped = (
            InvoiceItemAdjustment.objects.filter(
                operation=operation,
            )
            .select_related("officer", "adjustment")
            .order_by("-date", "-pk")
        )
        logger.debug(
            f"Item adjustments (grouped) fetched | count={len(item_adjustments_grouped)} | "
            f"operation_id={operation.pk}"
        )

        items_data = operation.get_items_data()
        logger.debug(
            f"Items movement data computed | items_count={len(items_data)} | "
            f"operation_id={operation.pk}"
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
            "has_capital_valuation": type(operation).has_capital_valuation,
            "capital_valuations": capital_valuations,
            "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
            "total_adjusted": total_adjusted,
        }
        return render(request, "app_operation/invoice_items_list.html", context)
