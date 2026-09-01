from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.app_base.logging_utils import audit_logger, logger
from apps.app_base.reversal import request_reversal, reversal_guard_error
from farm.shortcuts import get_object_or_404
from apps.app_operation.models.operation import Operation
from apps.app_operation.models.proxies import PROXY_MAP


def operation_reverse_view(request, pk):
    """Reverse a financial operation (critical audit operation)."""
    logger.debug(
        f"Fetching operation for reversal | operation_pk={pk} | "
        f"user={request.user.username}"
    )
    operation = get_object_or_404(
        Operation,
        pk=pk,
        error_message="Operation not found or has been deleted."
    )
    operation = Operation.objects.cast(operation)
    logger.debug(
        f"Operation loaded | operation_id={operation.pk} | "
        f"operation_type={operation.operation_type} | "
        f"is_reversed={operation.is_reversed} | is_reversal={operation.is_reversal}"
    )

    # Safety checks for reversibility
    error_msg = reversal_guard_error(operation, "operation")
    if error_msg:
        if operation.is_reversed:
            action = "reversal_attempt_already_reversed"
            details = {"reason": "already_reversed"}
        else:
            action = "reversal_attempt_on_reversal"
            details = {"reason": "is_itself_reversal"}
        logger.warning(f"{error_msg} | operation_id={operation.pk}")
        audit_logger.info(
            f"{action} | Operation:{operation.pk} | "
            f"user={request.user.username} | {details}"
        )
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    config = PROXY_MAP.get(operation.operation_type)
    if not config:
        error_msg = "Unsupported operation type."
        logger.error(
            f"{error_msg} | operation_type={operation.operation_type}"
        )
        audit_logger.info(
            f"reversal_attempt_unsupported_type | Operation:{operation.pk} | "
            f"user={request.user.username} | operation_type={operation.operation_type}"
        )
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    officer = request.user

    if request.method == "POST":
        logger.debug(
            f"Processing operation reversal | operation_id={operation.pk} | "
            f"operation_type={operation.operation_type} | officer={officer.username}"
        )
        response = request_reversal(
            request,
            operation,
            record_type="operation",
            reverse_call=lambda officer, reason: operation.reverse(
                reason=reason, officer=officer
            ),
            audit_success=lambda request, obj, reason, reversal: (
                f"operation_reversed | Operation:{obj.pk} | "
                f"user={request.user.username} | operation_type={obj.operation_type} | "
                f"label={obj.label} | reason={reason} | officer={request.user.username}"
            ),
            audit_failure=lambda request, obj, error, error_details: (
                f"operation_reversal_failed | Operation:{obj.pk} | "
                f"user={request.user.username} | error={error_details}"
            ),
            success_message=lambda request, obj, reason: (
                f"Successfully reversed {obj.label} #{obj.pk}"
            ),
            error_message=lambda error: f"Reversal failed: {str(error)}",
            redirect_to=lambda obj: redirect("operation_detail_view", pk=obj.pk),
            missing_reason_audit=lambda request, obj: (
                f"reversal_attempt_no_reason | Operation:{obj.pk} | "
                f"user={request.user.username} | reason=missing_reversal_reason"
            ),
            error_details_extra=lambda obj: {
                "operation_id": obj.pk,
                "operation_type": obj.operation_type,
            },
        )
        if response is not None:
            return response

    context = {
        "operation": operation,
        "config": {"label": operation.label},
        "today": timezone.now(),
    }
    return render(request, "app_operation/reverse_form.html", context)
