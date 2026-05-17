from django.conf import settings
from django.shortcuts import render

from apps.app_adjustment.models import Adjustment, InvoiceItemAdjustment
from apps.app_base.debug import DebugContext, debug_view
from apps.app_operation.models import Operation
from farm.shortcuts import get_object_or_404


@debug_view
def adjustments_list_view(request, pk):
    """Display all adjustments (accounting + item) for an operation.

    Shows both active and reversed adjustments, grouped by type, with
    full detail for each record.
    """
    with DebugContext.section(
        "Fetching operation for adjustments list",
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
            },
        )

    with DebugContext.section(
        "Fetching adjustments",
        {
            "operation_id": operation.pk,
        },
    ):
        # All accounting adjustments (including reversed)
        adjustments = (
            Adjustment.objects.filter(operation=operation)
            .select_related("officer", "reversal_of", "reversed_by")
            .order_by("-date", "-pk")
        )
        DebugContext.log(
            "Accounting adjustments fetched",
            {
                "count": len(adjustments),
                "operation_id": operation.pk,
            },
        )

        # All item adjustments (including reversed)
        item_adjustments = (
            InvoiceItemAdjustment.objects.filter(operation=operation)
            .select_related("officer", "adjustment", "reversal_of", "reversed_by")
            .prefetch_related("lines__invoice_item__product_template")
            .order_by("-date", "-pk")
        )
        DebugContext.log(
            "Item adjustments fetched",
            {
                "count": len(item_adjustments),
                "operation_id": operation.pk,
            },
        )

    context = {
        "operation": operation,
        "adjustments": adjustments,
        "item_adjustments": item_adjustments,
        "has_invoice": type(operation).has_invoice,
        "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
    }
    return render(request, "app_operation/adjustments_list.html", context)
