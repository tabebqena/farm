import traceback
from decimal import Decimal

from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.app_operation.models.operation import Operation
from apps.app_operation.models.proxies import PROXY_MAP
from apps.app_operation.forms import PaymentForm
from apps.app_transaction.models import Transaction


def record_transaction_payment(request, pk):
    operation = get_object_or_404(Operation, pk=pk)
    operation = Operation.objects.cast(operation)

    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                officer = request.user
                operation.create_payment_transaction(
                    amount=form.cleaned_data["amount"],
                    officer=officer,
                    date=form.cleaned_data["date"],
                    note=form.cleaned_data["note"],
                )
                messages.success(
                    request, f"Payment of {form.cleaned_data['amount']} recorded for Operation #{operation.pk}."
                )
                return redirect("operation_detail_view", pk=operation.pk)
            except Exception as e:
                traceback.print_exc()
                messages.error(request, f"Error: {str(e)}")
        # Form errors will be displayed in template
    else:
        form = PaymentForm(initial={
            "date": timezone.now().date(),
        })

    return render(
        request,
        "app_operation/add_payment_form.html",
        {
            "form": form,
            "operation": operation,
            "remaining_balance": operation.amount_remaining_to_settle,
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
        return HttpResponseBadRequest(
            f"Unsupported operation type: {operation.operation_type}"
        )
    data = proxy_cls.resolve_request(operation.source.pk, request)
    if not data.get("has_repayment"):
        return HttpResponseBadRequest(
            f"This operation does not accept repayments: {operation.operation_type}"
        )

    remaining_amount = operation.amount_remaining_to_repay

    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            if form.cleaned_data["amount"] > remaining_amount:
                form.add_error("amount", f"Amount exceeds remaining balance of {remaining_amount}.")
            else:
                try:
                    officer = request.user
                    transaction_type = data["repayment_transaction_type"]

                    with db_transaction.atomic():
                        Transaction.create(
                            source=operation.destination,
                            target=operation.source,
                            document=operation,
                            tx_type=transaction_type,
                            amount=form.cleaned_data["amount"],
                            officer=officer,
                            description=f"Repayment of operation #{operation.pk}",
                            note=form.cleaned_data["note"],
                            date=form.cleaned_data["date"],
                        )
                    messages.success(
                        request,
                        f"Repayment of {form.cleaned_data['amount']} recorded for Operation #{operation.pk}.",
                    )
                    return redirect("operation_detail_view", pk=operation.pk)
                except Exception as e:
                    traceback.print_exc()
                    messages.error(request, f"Error: {str(e)}")
        # Form errors will be displayed in template
    else:
        form = PaymentForm(initial={
            "date": timezone.now().date(),
        })

    return render(
        request,
        "app_operation/add_repayment_form.html",
        {
            "form": form,
            "operation": operation,
            "remaining_balance": remaining_amount,
        },
    )
