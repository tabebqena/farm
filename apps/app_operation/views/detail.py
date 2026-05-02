from django.shortcuts import render
from django.conf import settings
from decimal import Decimal

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

        adjustments = list(operation.adjustments.filter(reversal_of__isnull=True).order_by("date"))
        item_adjustments = list(operation.item_adjustments.filter(reversal_of__isnull=True).order_by("date"))
        DebugContext.log("Adjustments fetched", {
            "adjustment_count": len(adjustments),
            "item_adjustment_count": len(item_adjustments),
            "operation_id": operation.pk,
        })

    with DebugContext.section("Computing payment balance", {
        "operation_id": operation.pk,
    }):
        active_txs = [tx for tx in transactions if not getattr(tx, 'is_reversed', False) and not getattr(tx, 'reversal_of', None)]
        paid_amount = sum(
            tx.amount for tx in active_txs
            if 'payment' in tx.type.lower() or 'repayment' in tx.type.lower()
        ) or Decimal('0.00')
        outstanding_balance = (operation.effective_amount or operation.amount) - paid_amount
        DebugContext.log("Payment balance computed", {
            "paid_amount": float(paid_amount),
            "outstanding_balance": float(outstanding_balance),
            "operation_id": operation.pk,
        })

    context = {
        "operation": operation,
        "transactions": transactions,
        "items": items,
        "adjustments": adjustments,
        "item_adjustments": item_adjustments,
        "is_reversed": operation.is_reversed,
        "paid_amount": paid_amount,
        "outstanding_balance": outstanding_balance,
        "currency": getattr(settings, 'CURRENCY_SYMBOL', '$'),
    }
    return render(request, "app_operation/operation_detail.html", context)
