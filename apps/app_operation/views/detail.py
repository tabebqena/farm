from django.shortcuts import render

from farm.shortcuts import get_object_or_404
from apps.app_operation.models import Operation


def operation_detail_view(request, pk):
    operation = get_object_or_404(
        Operation,
        pk=pk,
        error_message="Operation not found or has been deleted."
    )
    operation = Operation.objects.cast(operation)

    # Prefetch related data for performance
    transactions = operation.get_all_transactions()

    items = operation.items.all() if type(operation).has_invoice else None

    # Group transactions for the UI
    context = {
        "operation": operation,
        "transactions": transactions,
        "items": items,
        "is_reversed": operation.is_reversed,
    }
    return render(request, "app_operation/operation_detail.html", context)
