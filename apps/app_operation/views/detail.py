from django.shortcuts import render
from django.conf import settings
from django.db.models import Sum, Q
from decimal import Decimal

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_operation.models import Operation
from apps.app_inventory.models import InventoryMovementLine


@debug_view
def operation_detail_view(request, pk):
    """Display operation details with all related transactions and items."""
    with DebugContext.section(
        "Fetching operation details",
        {
            "operation_pk": pk,
            "user": request.user.username,
        },
    ):
        operation = get_object_or_404(
            Operation, pk=pk, error_message="Operation not found or has been deleted."
        )
        operation = Operation.objects.cast(operation)
        print(dir(operation))
        DebugContext.success(
            "Operation loaded",
            {
                "operation_id": operation.pk,
                "operation_type": operation.operation_type,
                "is_reversed": operation.is_reversed,
            },
        )

    with DebugContext.section(
        "Fetching related transactions and items",
        {
            "operation_id": operation.pk,
        },
    ):
        transactions = operation.get_all_transactions()
        DebugContext.log(
            "Transactions fetched",
            {
                "count": len(transactions),
                "operation_id": operation.pk,
            },
        )

        items = operation.items.all() if type(operation).has_invoice else None
        item_count = items.count() if items else 0
        DebugContext.log(
            "Invoice items fetched",
            {
                "count": item_count,
                "has_invoice": type(operation).has_invoice,
                "operation_id": operation.pk,
            },
        )

        adjustments = list(
            operation.adjustments.filter(reversal_of__isnull=True).order_by("date")
        )
        item_adjustments = list(
            operation.item_adjustments.filter(reversal_of__isnull=True).order_by("date")
        )
        DebugContext.log(
            "Adjustments fetched",
            {
                "adjustment_count": len(adjustments),
                "item_adjustment_count": len(item_adjustments),
                "operation_id": operation.pk,
            },
        )

    with DebugContext.section(
        "Computing items_data for invoice items",
        {
            "operation_id": operation.pk,
            "has_invoice": type(operation).has_invoice,
        },
    ):
        items_data = []
        if items is not None:
            for item in items:
                moved_qty = InventoryMovementLine.objects.filter(
                    invoice_item=item,
                    reversal_of__isnull=True,
                ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")
                remaining_qty = item.quantity - moved_qty
                movement_lines = InventoryMovementLine.objects.filter(
                    invoice_item=item,
                    reversal_of__isnull=True,
                ).select_related("movement")
                items_data.append(
                    {
                        "item": item,
                        "moved_qty": moved_qty,
                        "remaining_qty": remaining_qty,
                        "is_fully_moved": remaining_qty <= Decimal("0.00"),
                        "movement_lines": movement_lines,
                    }
                )
        DebugContext.log(
            "Items data computed",
            {
                "items_count": len(items_data),
                "operation_id": operation.pk,
            },
        )

    with DebugContext.section(
        "Computing payment balance",
        {
            "operation_id": operation.pk,
        },
    ):
        active_txs = [
            tx
            for tx in transactions
            if not getattr(tx, "is_reversed", False)
            and not getattr(tx, "reversal_of", None)
        ]
        paid_amount = float(operation.amount_settled)
        outstanding_balance = float(operation.amount_remaining_to_settle)
        DebugContext.log(
            "Payment balance computed",
            {
                "paid_amount": paid_amount,
                "outstanding_balance": outstanding_balance,
                "operation_id": operation.pk,
            },
        )

        net_adjustment = (
            operation.effective_amount or Decimal("0.00")
        ) - operation.amount
        DebugContext.log(
            "Net adjustment computed",
            {
                "net_adjustment": float(net_adjustment),
                "operation_id": operation.pk,
            },
        )

        overpayment_amount = (
            operation.amount_settled - operation.total_settlable_amount
            if operation.is_overpayed_settled
            else Decimal("0.00")
        )
        DebugContext.log(
            "Overpayment computed",
            {
                "overpayment_amount": float(overpayment_amount),
                "operation_id": operation.pk,
            },
        )

        payment_transactions = [
            tx
            for tx in transactions
            if getattr(operation, "_payment_transaction_type", None)
            and tx.type == operation._payment_transaction_type
        ]
        DebugContext.log(
            "Payment transactions filtered",
            {
                "count": len(payment_transactions),
                "payment_type": getattr(operation, "_payment_transaction_type", None),
                "operation_id": operation.pk,
            },
        )

        repayment_transactions = [
            tx
            for tx in transactions
            if getattr(operation, "_repayment_transaction_type", None)
            and tx.type == operation._repayment_transaction_type
        ]
        DebugContext.log(
            "Repayment transactions filtered",
            {
                "count": len(repayment_transactions),
                "repayment_type": getattr(operation, "_repayment_transaction_type", None),
                "operation_id": operation.pk,
            },
        )

        over_repayment_amount = (
            operation.amount_repayed - operation.total_repayable_amount
            if operation.is_overpaid_repayed
            else Decimal("0.00")
        )
        DebugContext.log(
            "Over-repayment computed",
            {
                "over_repayment_amount": float(over_repayment_amount),
                "operation_id": operation.pk,
            },
        )

    context = {
        "operation": operation,
        "transactions": transactions,
        "payment_transactions": payment_transactions,
        "items": items,
        "items_data": items_data,
        "adjustments": adjustments,
        "item_adjustments": item_adjustments,
        "is_reversed": operation.is_reversed,
        "is_one_shot_operation": operation._is_one_shot_operation,
        "paid_amount": paid_amount,
        "outstanding_balance": outstanding_balance,
        "net_adjustment": net_adjustment,
        "overpayment_amount": overpayment_amount,
        "repayment_transactions": repayment_transactions,
        "over_repayment_amount": over_repayment_amount,
        "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
    }
    return render(request, "app_operation/operation_detail.html", context)
