import traceback

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.app_operation.models.operation import Operation
from apps.app_operation.models.proxies import PROXY_MAP


def operation_reverse_view(request, pk):
    operation = get_object_or_404(Operation, pk=pk)
    operation = Operation.objects.cast(operation)

    # Safety check: Prevent double reversal
    if operation.is_reversed:
        messages.warning(request, "This operation has already been reversed.")
        return redirect("operation_detail_view", pk=operation.pk)
    elif operation.is_reversal:
        messages.warning(
            request, "This operation is a reversal (You can't reverse it)."
        )
        return redirect("operation_detail_view", pk=operation.pk)

    config = PROXY_MAP.get(operation.operation_type)
    if not config:
        messages.warning(request, "Unsupported operation type.")
        return redirect("operation_detail_view", pk=operation.pk)

    officer = request.user

    if request.method == "POST":
        reason = request.POST.get("reversal_reason")
        if not reason:
            messages.error(request, "A reason for reversal is required.")

        else:
            try:
                operation.reverse(reason=reason, officer=officer)
                messages.success(
                    request, f"Successfully reversed {config.label} #{operation.pk}"
                )
                return redirect("operation_detail_view", pk=operation.pk)
            except Exception as e:
                traceback.print_exc()
                messages.error(request, f"Reversal failed: {str(e)}")

    context = {
        "operation": operation,
        "config": config,
        "today": timezone.now(),
    }
    return render(request, "app_operation/reverse_form.html", context)
