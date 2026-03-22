from django.contrib import messages
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_operation.models import Operation
from apps.app_operation.views.common import OPERATION_MAP


def operation_update_view(request, pk):
    operation = get_object_or_404(Operation, pk=pk)

    # Financial Protection: Do not allow editing reversed operations
    if operation.is_reversed:
        messages.error(request, "Cannot edit a reversed operation.")
        return redirect("operation_detail", pk=operation.pk)

    if request.method == "POST":
        try:
            with db_transaction.atomic():
                # Strictly only update non-financial fields
                operation.description = request.POST.get("description", "")
                operation.date = request.POST.get("date")
                operation.save()  # Mixin will sync the date to linked transactions

            messages.success(request, f"Update saved successfully.")
            return redirect("operation_detail", pk=operation.pk)
        except Exception as e:
            messages.error(request, f"Update Error: {str(e)}")

    context = {
        "operation": operation,
        "config": OPERATION_MAP.get(operation.operation_type, {}),
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
