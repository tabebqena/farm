from django.shortcuts import render

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_operation.models import Operation


@debug_view
def operation_detail_view(request, pk):
    """Display operation details with all related transactions and items."""
    with DebugContext.section("Fetching operation details", {
        "operation_pk": pk,
        "user": request.user.username,
    }):
        operation = get_object_or_404(
            Operation,
            pk=pk,
            error_message="Operation not found or has been deleted."
        )
        operation = Operation.objects.cast(operation)
        DebugContext.success("Operation loaded", {
            "operation_id": operation.pk,
            "operation_type": operation.operation_type,
            "is_reversed": operation.is_reversed,
        })

    with DebugContext.section("Fetching related transactions and items", {
        "operation_id": operation.pk,
    }):
        transactions = operation.get_all_transactions()
        DebugContext.log("Transactions fetched", {
            "count": len(transactions),
            "operation_id": operation.pk,
        })

        items = operation.items.all() if type(operation).has_invoice else None
        item_count = items.count() if items else 0
        DebugContext.log("Invoice items fetched", {
            "count": item_count,
            "has_invoice": type(operation).has_invoice,
            "operation_id": operation.pk,
        })

    context = {
        "operation": operation,
        "transactions": transactions,
        "items": items,
        "is_reversed": operation.is_reversed,
    }
    return render(request, "app_operation/operation_detail.html", context)
