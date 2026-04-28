import traceback

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_operation.models.operation import Operation
from apps.app_operation.models.proxies import PROXY_MAP


@debug_view
def operation_reverse_view(request, pk):
    """Reverse a financial operation (critical audit operation)."""
    with DebugContext.section("Fetching operation for reversal", {
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
            "is_reversal": operation.is_reversal,
        })

    # Safety checks for reversibility
    if operation.is_reversed:
        error_msg = "This operation has already been reversed."
        DebugContext.warn(error_msg, {"operation_id": operation.pk})
        DebugContext.audit(
            action="reversal_attempt_already_reversed",
            entity_type="Operation",
            entity_id=operation.pk,
            details={"reason": "already_reversed"},
            user=request.user.username
        )
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    if operation.is_reversal:
        error_msg = "This operation is a reversal (You can't reverse it)."
        DebugContext.warn(error_msg, {"operation_id": operation.pk})
        DebugContext.audit(
            action="reversal_attempt_on_reversal",
            entity_type="Operation",
            entity_id=operation.pk,
            details={"reason": "is_itself_reversal"},
            user=request.user.username
        )
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    config = PROXY_MAP.get(operation.operation_type)
    if not config:
        error_msg = "Unsupported operation type."
        DebugContext.error(error_msg, data={"operation_type": operation.operation_type})
        DebugContext.audit(
            action="reversal_attempt_unsupported_type",
            entity_type="Operation",
            entity_id=operation.pk,
            details={"operation_type": operation.operation_type},
            user=request.user.username
        )
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    officer = request.user

    if request.method == "POST":
        with DebugContext.section("Processing operation reversal", {
            "operation_id": operation.pk,
            "operation_type": operation.operation_type,
            "officer": officer.username,
        }):
            reason = request.POST.get("reversal_reason", "").strip()

            if not reason:
                error_msg = "A reason for reversal is required."
                DebugContext.warn(error_msg, {"operation_id": operation.pk})
                DebugContext.audit(
                    action="reversal_attempt_no_reason",
                    entity_type="Operation",
                    entity_id=operation.pk,
                    details={"reason": "missing_reversal_reason"},
                    user=request.user.username
                )
                messages.error(request, error_msg)
            else:
                try:
                    with DebugContext.section("Executing transaction reversal"):
                        operation.reverse(reason=reason, officer=officer)

                    DebugContext.success("Operation reversed successfully", {
                        "operation_id": operation.pk,
                        "operation_type": config.label,
                        "reversal_reason": reason[:100],
                    })
                    DebugContext.audit(
                        action="operation_reversed",
                        entity_type="Operation",
                        entity_id=operation.pk,
                        details={
                            "operation_type": operation.operation_type,
                            "label": config.label,
                            "reason": reason,
                            "officer": officer.username,
                        },
                        user=request.user.username
                    )

                    messages.success(
                        request, f"Successfully reversed {config.label} #{operation.pk}"
                    )
                    return redirect("operation_detail_view", pk=operation.pk)
                except Exception as e:
                    error_details = {
                        "exception_type": type(e).__name__,
                        "error_message": str(e),
                        "operation_id": operation.pk,
                        "operation_type": operation.operation_type,
                        "officer": officer.username,
                        "traceback": traceback.format_exc(),
                    }
                    DebugContext.error("Operation reversal failed", e, data=error_details)
                    DebugContext.audit(
                        action="operation_reversal_failed",
                        entity_type="Operation",
                        entity_id=operation.pk,
                        details=error_details,
                        user=request.user.username
                    )
                    traceback.print_exc()
                    messages.error(request, f"Reversal failed: {str(e)}")

    context = {
        "operation": operation,
        "config": config,
        "today": timezone.now(),
    }
    return render(request, "app_operation/reverse_form.html", context)
