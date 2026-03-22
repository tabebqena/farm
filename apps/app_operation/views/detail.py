from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.views.generic import DetailView

from apps.app_operation.models import Operation


class CashInjectionDetailView(LoginRequiredMixin, DetailView):
    model = Operation
    template_name = "app_cash_injection/cash_injection_detail.html"
    context_object_name = "injection"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch linked transactions for the audit trail
        context["transactions"] = self.object.get_all_transactions().select_related(
            "source",
            "target",
        )
        context["reversal_of"] = self.object.reversal_of
        context["reversed_by"] = getattr(self.object, "reversed_by", None)
        context["entity"] = self.object.owner

        return context


def operation_detail_view(request, pk):
    operation = get_object_or_404(Operation, pk=pk)

    # Prefetch related data for performance
    transactions = operation.get_all_transactions()
    # .select_related(
    #     "type", "source", "target"
    # )

    # issuance_type = operation._get_issuance_transaction_type()
    # issuance_tx = []
    # if issuance_type:
    #     issuance_tx = transactions.filter(type=issuance_type)
    # payment_type = operation._get_payment_transaction_type()
    # payment_tx = []
    # if payment_type:
    #     payment_tx = transactions.filter(type=payment_type)

    # Group transactions for the UI
    context = {
        "operation": operation,
        "transactions": transactions,
        # "issuance_tx": issuance_tx,
        # "payment_tx": payment_tx,
        "is_reversed": operation.is_reversed,
    }
    # if operation.operation_type == OperationType.LOAN:
    #     context["repayments"] = Transaction.objects.filter(
    #         # content_type=ContentType.objects.get_for_model(Operation),
    #         object_id=operation.pk,
    #         type=TransactionType.LOAN_REPAYMENT,
    #         reversal_of=None,
    #     )
    return render(request, "app_operation/operation_detail.html", context)
