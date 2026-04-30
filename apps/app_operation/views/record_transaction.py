import traceback
from decimal import Decimal

from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_operation.models.operation import Operation
from apps.app_operation.models.proxies import PROXY_MAP
from apps.app_operation.forms import PaymentForm
from apps.app_transaction.models import Transaction


@debug_view
def record_transaction_payment(request, pk):
    """Record a payment transaction for an operation."""
    with DebugContext.section("Fetching operation for payment", {"operation_pk": pk, "user": request.user.username}):
        operation = get_object_or_404(
            Operation,
            pk=pk,
            error_message="Operation not found or has been deleted."
        )
        operation = Operation.objects.cast(operation)
        DebugContext.success("Operation loaded", {
            "operation_id": operation.pk,
            "operation_type": operation.operation_type,
            "remaining_to_settle": str(operation.amount_remaining_to_settle),
        })

    if request.method == "POST":
        with DebugContext.section("Processing payment transaction", {
            "operation_pk": pk,
            "user": request.user.username,
        }):
            form = PaymentForm(request.POST)
            if form.is_valid():
                try:
                    officer = request.user
                    amount = form.cleaned_data["amount"]
                    with DebugContext.section("Creating payment transaction", {
                        "amount": str(amount),
                        "date": str(form.cleaned_data["date"]),
                    }):
                        operation.create_payment_transaction(
                            amount=amount,
                            officer=officer,
                            date=form.cleaned_data["date"],
                            note=form.cleaned_data["note"],
                        )
                        DebugContext.success("Payment transaction created", {
                            "operation_id": operation.pk,
                            "amount": str(amount),
                        })
                        DebugContext.audit(
                            action="payment_transaction_created",
                            entity_type="Transaction",
                            entity_id=operation.pk,
                            details={
                                "operation_id": operation.pk,
                                "amount": str(amount),
                            },
                            user=request.user.username
                        )
                    messages.success(
                        request, f"Payment of {amount} recorded for Operation #{operation.pk}."
                    )
                    return redirect("operation_detail_view", pk=operation.pk)
                except Exception as e:
                    traceback.print_exc()
                    error_details = {
                        "exception_type": type(e).__name__,
                        "error_message": str(e),
                        "operation_id": operation.pk,
                    }
                    DebugContext.error("Payment transaction creation failed", e, error_details)
                    DebugContext.audit(
                        action="payment_transaction_failed",
                        entity_type="Transaction",
                        entity_id=operation.pk,
                        details=error_details,
                        user=request.user.username
                    )
                    messages.error(request, f"Error: {str(e)}")
            else:
                error_details = {"form_errors": str(form.errors)}
                DebugContext.warn("Payment form validation failed", error_details)
                DebugContext.audit(
                    action="payment_form_validation_failed",
                    entity_type="Transaction",
                    entity_id=operation.pk,
                    details=error_details,
                    user=request.user.username
                )
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


@debug_view
def record_transaction_repayment(request, pk):
    """Record a repayment transaction for an operation."""
    with DebugContext.section("Fetching operation for repayment", {"operation_pk": pk, "user": request.user.username}):
        operation = Operation.objects.filter(pk=pk).first()
        if not operation:
            DebugContext.error("Operation not found", None, {"operation_pk": pk})
            DebugContext.audit(
                action="repayment_operation_not_found",
                entity_type="Operation",
                entity_id=None,
                details={"operation_pk": pk},
                user=request.user.username
            )
            return HttpResponseNotFound("No Operation matches the provided info")

        # Cast to correct proxy so amount_remaining_to_repay is available
        operation = Operation.objects.cast(operation)
        DebugContext.success("Operation loaded", {
            "operation_id": operation.pk,
            "operation_type": operation.operation_type,
        })

    with DebugContext.section("Validating repayment eligibility", {
        "operation_id": operation.pk,
        "operation_type": operation.operation_type,
    }):
        proxy_cls = PROXY_MAP.get(operation.operation_type)
        if not proxy_cls:
            error_msg = f"Unsupported operation type: {operation.operation_type}"
            DebugContext.error(error_msg, None, {"operation_type": operation.operation_type})
            DebugContext.audit(
                action="repayment_unsupported_operation_type",
                entity_type="Operation",
                entity_id=operation.pk,
                details={"operation_type": operation.operation_type},
                user=request.user.username
            )
            return HttpResponseBadRequest(error_msg)

        data = proxy_cls.resolve_request(operation.source.pk, request)
        if not data.get("has_repayment"):
            error_msg = f"This operation does not accept repayments: {operation.operation_type}"
            DebugContext.warn("Operation does not accept repayments", {"operation_type": operation.operation_type})
            DebugContext.audit(
                action="repayment_not_accepted",
                entity_type="Operation",
                entity_id=operation.pk,
                details={"operation_type": operation.operation_type},
                user=request.user.username
            )
            return HttpResponseBadRequest(error_msg)
        DebugContext.success("Repayment validation passed", {"operation_id": operation.pk})

    remaining_amount = operation.amount_remaining_to_repay

    if request.method == "POST":
        with DebugContext.section("Processing repayment transaction", {
            "operation_pk": pk,
            "user": request.user.username,
        }):
            form = PaymentForm(request.POST)
            if form.is_valid():
                if form.cleaned_data["amount"] > remaining_amount:
                    error_msg = f"Amount exceeds remaining balance of {remaining_amount}."
                    form.add_error("amount", error_msg)
                    DebugContext.warn("Repayment amount exceeds remaining balance", {
                        "requested_amount": str(form.cleaned_data["amount"]),
                        "remaining_amount": str(remaining_amount),
                    })
                else:
                    try:
                        officer = request.user
                        transaction_type = data["repayment_transaction_type"]
                        amount = form.cleaned_data["amount"]

                        with db_transaction.atomic():
                            with DebugContext.section("Creating repayment transaction", {
                                "amount": str(amount),
                                "transaction_type": transaction_type,
                            }):
                                Transaction.create(
                                    source=operation.destination,
                                    target=operation.source,
                                    document=operation,
                                    tx_type=transaction_type,
                                    amount=amount,
                                    officer=officer,
                                    description=f"Repayment of operation #{operation.pk}",
                                    note=form.cleaned_data["note"],
                                    date=form.cleaned_data["date"],
                                )
                                DebugContext.success("Repayment transaction created", {
                                    "operation_id": operation.pk,
                                    "amount": str(amount),
                                })
                                DebugContext.audit(
                                    action="repayment_transaction_created",
                                    entity_type="Transaction",
                                    entity_id=operation.pk,
                                    details={
                                        "operation_id": operation.pk,
                                        "amount": str(amount),
                                    },
                                    user=request.user.username
                                )
                        messages.success(
                            request,
                            f"Repayment of {amount} recorded for Operation #{operation.pk}.",
                        )
                        return redirect("operation_detail_view", pk=operation.pk)
                    except Exception as e:
                        traceback.print_exc()
                        error_details = {
                            "exception_type": type(e).__name__,
                            "error_message": str(e),
                            "operation_id": operation.pk,
                        }
                        DebugContext.error("Repayment transaction creation failed", e, error_details)
                        DebugContext.audit(
                            action="repayment_transaction_failed",
                            entity_type="Transaction",
                            entity_id=operation.pk,
                            details=error_details,
                            user=request.user.username
                        )
                        messages.error(request, f"Error: {str(e)}")
            else:
                error_details = {"form_errors": str(form.errors)}
                DebugContext.warn("Repayment form validation failed", error_details)
                DebugContext.audit(
                    action="repayment_form_validation_failed",
                    entity_type="Transaction",
                    entity_id=operation.pk,
                    details=error_details,
                    user=request.user.username
                )
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
