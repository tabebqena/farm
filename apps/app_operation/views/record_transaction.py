import traceback
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import BadRequest
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.app_entity.models import Entity
from apps.app_operation.models.operation import Operation, OperationType
from apps.app_operation.views.common import parse_config
from apps.app_transaction.models import Transaction


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
    operation = Operation.objects.filter(pk=pk).first()
    if not operation:
        return HttpResponseNotFound("No Operation matches the provided info")

    # Cast to correct proxy so amount_remaining_to_repay is available
    operation = Operation.objects.cast(operation)

    canonical_op_type = operation.operation_type
    try:
        data = parse_config(canonical_op_type, operation.source.pk, request)
        if not data.get("has_repayment"):
            return HttpResponseBadRequest(
                f"This operation does not accept repayments: {canonical_op_type}"
            )
    except (BadRequest, Exception) as e:
        traceback.print_exc()
        return HttpResponseBadRequest(str(e))

    # Safe defaults for both GET and POST
    date = request.POST.get("date") or timezone.now().date()
    note = request.POST.get("note") or ""
    amount_raw = request.POST.get("amount", "0") or "0"

    if request.method == "POST":
        try:
            amount = Decimal(amount_raw)
        except Exception:
            messages.error(request, "Invalid amount value.")
            return redirect("operation_detail_view", pk=operation.pk)

        remaining_amount = operation.amount_remaining_to_repay

        if amount <= 0:
            messages.error(request, "Amount must be greater than zero.")
        elif amount > remaining_amount:
            messages.error(
                request,
                f"Amount {amount} exceeds remaining balance {remaining_amount}.",
            )
        else:
            try:
                officer = get_object_or_404(Entity, user=request.user)
                transaction_type = data["repayment_transaction_type"]

                with db_transaction.atomic():
                    Transaction.create(
                        source=operation.destination.fund,
                        target=operation.source.fund,
                        document=operation,
                        type=transaction_type,
                        amount=amount,
                        officer=officer,
                        description=f"Repayment of operation #{operation.pk}",
                        note=note,
                        date=date,
                    )
                messages.success(
                    request,
                    f"Repayment of {amount} recorded for Operation #{operation.pk}.",
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
            "remaining_balance": operation.amount_remaining_to_repay,
            "date": date,
            "amount": amount_raw,
            "note": note,
        },
    )
