from django.shortcuts import get_object_or_404, render

from apps.app_operation.models import Operation


def operation_detail_view(request, pk):
    operation = get_object_or_404(Operation, pk=pk)
    operation = Operation.objects.cast(operation)

    # Prefetch related data for performance
    transactions = operation.get_all_transactions()

    # Group transactions for the UI
    context = {
        "operation": operation,
        "transactions": transactions,
        # "issuance_tx": issuance_tx,
        # "payment_tx": payment_tx,
        "is_reversed": operation.is_reversed,
    }
    return render(request, "app_operation/operation_detail.html", context)
