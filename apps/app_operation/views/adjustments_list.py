from django.conf import settings
from django.shortcuts import render
from django.views import View

from apps.app_adjustment.models import Adjustment, InvoiceItemAdjustment
from apps.app_base.logging_utils import logger
from apps.app_operation.models import Operation
from farm.shortcuts import get_object_or_404


class AdjustmentsListView(View):
    """Display all adjustments (accounting + item) for an operation.

    Shows both active and reversed adjustments, grouped by type, with
    full detail for each record.
    """

    def get(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        logger.debug(
            f"Fetching operation for adjustments list | operation_pk={pk} | "
            f"user={request.user.username}"
        )
        operation = get_object_or_404(
            Operation, pk=pk, error_message="Operation not found or has been deleted."
        )
        operation = Operation.objects.cast(operation)
        logger.debug(
            f"Operation loaded | operation_id={operation.pk} | "
            f"operation_type={operation.operation_type}"
        )

        logger.debug(f"Fetching adjustments | operation_id={operation.pk}")
        # All accounting adjustments (including reversed)
        adjustments = (
            Adjustment.objects.filter(operation=operation)
            .select_related("officer", "reversal_of", "reversed_by")
            .order_by("-date", "-pk")
        )
        logger.debug(
            f"Accounting adjustments fetched | count={len(adjustments)} | "
            f"operation_id={operation.pk}"
        )

        # All item adjustments (including reversed)
        item_adjustments = (
            InvoiceItemAdjustment.objects.filter(operation=operation)
            .select_related("officer", "adjustment", "reversal_of", "reversed_by")
            .prefetch_related("lines__invoice_item__product_template")
            .order_by("-date", "-pk")
        )
        logger.debug(
            f"Item adjustments fetched | count={len(item_adjustments)} | "
            f"operation_id={operation.pk}"
        )

        context = {
            "operation": operation,
            "adjustments": adjustments,
            "item_adjustments": item_adjustments,
            "has_invoice": type(operation).has_invoice,
            "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
        }
        return render(request, "app_operation/adjustments_list.html", context)
