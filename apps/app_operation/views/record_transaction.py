import traceback
from decimal import Decimal

from django.contrib import messages
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.app_entity.models import Entity
from apps.app_operation.models import Operation, OperationType
from apps.app_transaction.models import Transaction
from apps.app_transaction.transaction_type import TransactionType


def record_transaction_payment(request, pk):
    operation = get_object_or_404(Operation, pk=pk, operation_type=OperationType.LOAN)

    # Calculate the current balance based on existing transactions
    # (Assuming payments are marked or have a specific flow)
    # total_repaid = operation.transactions.filter(is_repayment=True)...
    amount = request.POST.get("amount") or 0
    date = request.POST.get("date") or timezone.now().date()
    note = request.POST.get("note") or ""

    if request.method == "POST":
        try:
            officer = get_object_or_404(Entity, user=request.user)

            with db_transaction.atomic():
                # We create a new Transaction inside the SAME operation
                # This transaction flips the direction of the original loan
                tx = Transaction.create(
                    source=operation.destination.fund,  # Debtor pays
                    target=operation.source.fund,  # Creditor receives
                    document=operation,
                    type=operation._payment_transaction_type,
                    amount=Decimal(amount),
                    officer=officer,
                    description=f"Payment of {operation.pk}",
                    note=note,
                    date=date,
                )
            messages.success(
                request, f"Transaction of {amount} added to Operation #{operation.pk}"
            )
            return redirect("operation_detail_view", pk=operation.pk)
        except Exception as e:
            traceback.print_exc()
            messages.error(request, f"Error: {str(e)}")

    return render(
        request,
        "app_operation/add_payment_form.html",
        {
            "operation": operation,
            "date": date,
            "amount": amount,
            "note": note,
        },
    )


def record_transaction_repayment(request, pk):
    operation = get_object_or_404(Operation, pk=pk, operation_type=OperationType.LOAN)

    # Calculate the current balance based on existing transactions
    # (Assuming repayments are marked or have a specific flow)
    # total_repaid = operation.transactions.filter(is_repayment=True)...
    amount = request.POST.get("amount") or 0
    date = request.POST.get("date") or timezone.now().date()
    note = request.POST.get("note") or ""

    if request.method == "POST":
        try:
            officer = get_object_or_404(Entity, user=request.user)

            with db_transaction.atomic():
                # We create a new Transaction inside the SAME operation
                # This transaction flips the direction of the original loan
                tx = Transaction.create(
                    source=operation.destination.fund,  # Debtor pays
                    target=operation.source.fund,  # Creditor receives
                    document=operation,
                    type=TransactionType.LOAN_REPAYMENT,
                    amount=Decimal(amount),
                    officer=officer,
                    description=f"Repayment of {operation.pk}",
                    note=note,
                    date=date,
                )
            messages.success(
                request, f"Transaction of {amount} added to Operation #{operation.pk}"
            )
            return redirect("operation_detail_view", pk=operation.pk)
        except Exception as e:
            traceback.print_exc()
            messages.error(request, f"Error: {str(e)}")

    return render(
        request,
        "app_operation/add_repayment_form.html",
        {
            "operation": operation,
            "date": date,
            "amount": amount,
            "note": note,
        },
    )
