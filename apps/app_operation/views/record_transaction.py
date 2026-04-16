import traceback
from decimal import Decimal

from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.app_entity.models import Entity
from apps.app_operation.models.operation import Operation
from apps.app_operation.models.proxies import PROXY_MAP
from apps.app_transaction.models import Transaction


def record_transaction_payment(request, pk):
    operation = get_object_or_404(Operation, pk=pk)
    operation = Operation.objects.cast(operation)

    date = request.POST.get("date") or timezone.now().date()
    note = request.POST.get("note") or ""
    amount_raw = request.POST.get("amount", "0") or "0"

    if request.method == "POST":
        try:
            amount = Decimal(amount_raw)
        except Exception:
            messages.error(request, "Invalid amount value.")
            return redirect("operation_detail_view", pk=operation.pk)

        try:
            officer = get_object_or_404(Entity, user=request.user)
            operation.create_payment_transaction(
                amount=amount,
                officer=officer,
                date=date,
                note=note,
            )
            messages.success(
                request, f"Payment of {amount} recorded for Operation #{operation.pk}."
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
            "remaining_balance": operation.amount_remaining_to_settle,
            "date": date,
            "amount": amount_raw,
            "note": note,
        },
    )


def record_transaction_repayment(request, pk):
    operation = Operation.objects.filter(pk=pk).first()
    if not operation:
        return HttpResponseNotFound("No Operation matches the provided info")

    # Cast to correct proxy so amount_remaining_to_repay is available
    operation = Operation.objects.cast(operation)

    proxy_cls = PROXY_MAP.get(operation.operation_type)
    if not proxy_cls:
        return HttpResponseBadRequest(f"Unsupported operation type: {operation.operation_type}")
    data = proxy_cls.resolve_request(operation.source.pk, request)
    if not data.get("has_repayment"):
        return HttpResponseBadRequest(
            f"This operation does not accept repayments: {operation.operation_type}"
        )

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
