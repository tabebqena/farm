import traceback

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_entity.models import Entity
from apps.app_personal_operation.models import Operation
from apps.app_personal_operation.views.common import OPERATION_MAP
from django.utils import timezone


def operation_reverse_view(request, pk):
    operation = get_object_or_404(Operation, pk=pk)

    # Safety check: Prevent double reversal
    if operation.is_reversed:
        messages.warning(request, "This operation has already been reversed.")
        return redirect("operation_detail_view", pk=operation.pk)
    elif operation.is_reversal:
        messages.warning(
            request, "This operation is a reversal (You can't reverse it)."
        )
        return redirect("operation_detail_view", pk=operation.pk)

    config = OPERATION_MAP.get(
        operation.operation_type,
    )
    if not config:
        messages.warning(request, "Unsupported operation type.")
        return redirect("operation_detail_view", pk=operation.pk)

    officer = get_object_or_404(Entity, user=request.user)

    if request.method == "POST":
        reason = request.POST.get("reversal_reason")
        if not reason:
            messages.error(request, "A reason for reversal is required.")

        else:
            try:
                operation.reverse(reason=reason, officer=officer)
                messages.success(
                    request, f"Successfully reversed {config['label']} #{operation.pk}"
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
    return render(request, "app_personal_operation/reverse_form.html", context)


# @login_required
# def cash_injection_reverse_view(request, pk):
#     # 1. Fetch the injection and ensure the officer exists
#     injection = get_object_or_404(Operation, pk=pk)
#     # Resolve the officer (staff member) performing the reversal
#     officer_entity = get_object_or_404(Entity, user=request.user)
#     if not officer_entity.user.is_staff:
#         return HttpResponseBadRequest("Officer required")

#     if request.method == "GET":
#         return render(
#             request,
#             "app_cash_injection/cash_injection_reverse.html",
#             {"object": injection},
#         )

#     # 2. Extract reason from the form
#     reason = request.POST.get("reason", "No reason provided.")
#     try:
#         with db_transaction.atomic():
#             # This calls the method from your ReversableModel mixin
#             # It handles:
#             # - Validating it's not already reversed
#             # - Reversing the associated Ledger Transactions
#             # - Creating the 'Cloned' reversal Operation record
#             reversal_record = injection.reverse(officer=officer_entity, reason=reason)

#         messages.success(
#             request,
#             f"Successfully reversed Injection #{injection.pk}. Reversal record: #{reversal_record.pk}",
#         )
#     except Exception as e:
#         traceback.print_exc()
#         messages.error(request, f"Reversal failed: {str(e)}")

#     # Redirect back to the person's capital history or the injection list
#     return redirect("cash_list_view", person_pk=injection.destination.pk)
