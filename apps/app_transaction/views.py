import traceback

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.app_base.debug import DebugContext, debug_view
from apps.app_transaction.models import Transaction


@debug_view
def transaction_reverse_view(request, pk):
    """Reverse an individual financial transaction (critical audit operation).

    This operates at the Transaction level — unlike operation-level reversal
    which reverses the entire operation including all its transactions, this
    view reverses a single transaction by swapping its source and target
    (creating a mirror-image reversal transaction).
    """
    with DebugContext.section("Fetching transaction for reversal", {
        "transaction_pk": pk,
        "user": request.user.username,
    }):
        transaction = Transaction.objects.filter(pk=pk).first()
        if not transaction:
            DebugContext.error("Transaction not found", None, {
                "transaction_pk": pk,
            })
            messages.error(request, "Transaction not found.")
            return redirect("home")

        DebugContext.success("Transaction loaded", {
            "transaction_pk": transaction.pk,
            "type": transaction.type,
            "amount": float(transaction.amount),
            "source": str(transaction.source),
            "target": str(transaction.target),
            "is_reversed": transaction.is_reversed,
            "is_reversal": transaction.is_reversal,
        })

    # Safety checks for reversibility
    if transaction.is_reversed:
        error_msg = "This transaction has already been reversed."
        DebugContext.warn(error_msg, {"transaction_pk": transaction.pk})
        DebugContext.audit(
            action="reversal_attempt_already_reversed",
            entity_type="Transaction",
            entity_id=transaction.pk,
            details={"reason": "already_reversed"},
            user=request.user.username,
        )
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=transaction.object_id)

    if transaction.is_reversal:
        error_msg = "This transaction is a reversal (You can't reverse it)."
        DebugContext.warn(error_msg, {"transaction_pk": transaction.pk})
        DebugContext.audit(
            action="reversal_attempt_on_reversal",
            entity_type="Transaction",
            entity_id=transaction.pk,
            details={"reason": "is_itself_reversal"},
            user=request.user.username,
        )
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=transaction.object_id)

    # Block reversing transactions that belong to one-shot operations.
    # One-shot operations (e.g. CashInjection, Birth, CapitalGain/Loss, etc.)
    # handle all their transactions implicitly during operation-level reversal.
    # Allowing manual transaction reversal would break consistency for these.
    operation = transaction.document
    if operation and getattr(operation, "_is_one_shot_operation", False):
        error_msg = (
            "This transaction belongs to a one-shot operation and cannot be "
            "reversed individually. Reverse the entire operation instead."
        )
        DebugContext.warn(error_msg, {
            "transaction_pk": transaction.pk,
            "operation_pk": operation.pk,
            "operation_type": operation.operation_type,
        })
        DebugContext.audit(
            action="reversal_attempt_on_one_shot_operation",
            entity_type="Transaction",
            entity_id=transaction.pk,
            details={
                "reason": "one_shot_operation",
                "operation_pk": operation.pk,
                "operation_type": operation.operation_type,
            },
            user=request.user.username,
        )
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=transaction.object_id)

    if request.method == "POST":
        with DebugContext.section("Processing transaction reversal", {
            "transaction_pk": transaction.pk,
            "type": transaction.type,
            "officer": request.user.username,
        }):
            reason = request.POST.get("reversal_reason", "").strip()

            if not reason:
                error_msg = "A reason for reversal is required."
                DebugContext.warn(error_msg, {"transaction_pk": transaction.pk})
                DebugContext.audit(
                    action="reversal_attempt_no_reason",
                    entity_type="Transaction",
                    entity_id=transaction.pk,
                    details={"reason": "missing_reversal_reason"},
                    user=request.user.username,
                )
                messages.error(request, error_msg)
            else:
                try:
                    with DebugContext.section("Executing transaction reversal"):
                        officer = request.user
                        reversal = transaction.reverse(
                            officer=officer,
                            reason=reason,
                        )

                    DebugContext.success("Transaction reversed successfully", {
                        "transaction_pk": transaction.pk,
                        "reversal_pk": reversal.pk,
                        "reason": reason[:100],
                    })
                    DebugContext.audit(
                        action="transaction_reversed",
                        entity_type="Transaction",
                        entity_id=transaction.pk,
                        details={
                            "reversal_pk": reversal.pk,
                            "type": transaction.type,
                            "amount": float(transaction.amount),
                            "reason": reason,
                            "officer": request.user.username,
                        },
                        user=request.user.username,
                    )

                    messages.success(
                        request,
                        f"Transaction #{transaction.pk} reversed successfully.",
                    )
                    return redirect("operation_detail_view", pk=transaction.object_id)
                except Exception as e:
                    error_details = {
                        "exception_type": type(e).__name__,
                        "error_message": str(e),
                        "transaction_pk": transaction.pk,
                        "officer": request.user.username,
                        "traceback": traceback.format_exc(),
                    }
                    DebugContext.error(
                        "Transaction reversal failed", e, data=error_details
                    )
                    DebugContext.audit(
                        action="transaction_reversal_failed",
                        entity_type="Transaction",
                        entity_id=transaction.pk,
                        details=error_details,
                        user=request.user.username,
                    )
                    traceback.print_exc()
                    messages.error(request, f"Reversal failed: {str(e)}")

    context = {
        "transaction": transaction,
        "today": timezone.now(),
    }
    return render(request, "app_transaction/reverse_form.html", context)
