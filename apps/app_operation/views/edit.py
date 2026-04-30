from django.contrib import messages
from django.db import transaction as db_transaction
from django.shortcuts import redirect, render

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_operation.models.operation import Operation
from apps.app_operation.models.proxies import PROXY_MAP


@debug_view
def operation_update_view(request, pk):
    """Update non-financial fields of an operation."""
    with DebugContext.section("Fetching operation for update", {"operation_pk": pk, "user": request.user.username}):
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
        })

    # Financial Protection: Do not allow editing reversed operations
    if operation.is_reversed:
        error_msg = "Cannot edit a reversed operation."
        DebugContext.warn(error_msg, {"operation_id": operation.pk})
        DebugContext.audit(
            action="operation_update_attempt_on_reversed",
            entity_type="Operation",
            entity_id=operation.pk,
            details={"reason": "operation_already_reversed"},
            user=request.user.username
        )
        messages.error(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    if request.method == "POST":
        with DebugContext.section("Processing operation update", {
            "operation_pk": pk,
            "user": request.user.username,
        }):
            try:
                with db_transaction.atomic():
                    # Strictly only update non-financial fields
                    old_description = operation.description
                    old_date = operation.date

                    operation.description = request.POST.get("description", "")
                    operation.date = request.POST.get("date")
                    operation.save()  # Mixin will sync the date to linked transactions

                    DebugContext.success("Operation updated", {
                        "operation_id": operation.pk,
                        "old_description": old_description,
                        "new_description": operation.description,
                        "old_date": str(old_date),
                        "new_date": str(operation.date),
                    })
                    DebugContext.audit(
                        action="operation_updated",
                        entity_type="Operation",
                        entity_id=operation.pk,
                        details={
                            "operation_type": operation.operation_type,
                            "description_changed": old_description != operation.description,
                            "date_changed": old_date != operation.date,
                        },
                        user=request.user.username
                    )

                messages.success(request, "Update saved successfully.")
                return redirect("operation_detail_view", pk=operation.pk)
            except Exception as e:
                error_details = {
                    "exception_type": type(e).__name__,
                    "error_message": str(e),
                    "operation_id": operation.pk,
                }
                DebugContext.error("Operation update failed", e, error_details)
                DebugContext.audit(
                    action="operation_update_failed",
                    entity_type="Operation",
                    entity_id=operation.pk,
                    details=error_details,
                    user=request.user.username
                )
                messages.error(request, f"Update Error: {str(e)}")

    context = {
        "operation": operation,
        "config": PROXY_MAP.get(operation.operation_type),
        "is_update": True,
    }
    return render(request, "app_operation/generic_edit_form.html", context)


# class CashInjectionUpdateView(LoginRequiredMixin, UpdateView):
#     model = Operation
#     fields = ["date", "description"]  # Only allow editing non-critical fields
#     template_name = "app_cash_injection/cash_injection_edit.html"

#     def get_success_url(self):
#         return reverse("operation_detail_view", kwargs={"pk": self.object.pk})

#     def form_valid(self, form):
#         messages.success(self.request, "Entry updated successfully.")
#         return super().form_valid(form)
