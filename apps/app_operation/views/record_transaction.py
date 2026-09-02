"""Payment / repayment recording views.

Provides the shared :class:`_TransactionRecordView` base and its subclasses
:class:`RecordTransactionPaymentView` / :class:`RecordTransactionRepaymentView`
for settling an operation's outstanding amount.
"""

from django.conf import settings
from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from apps.app_base.logging_utils import audit_logger, build_error_details, logger
from apps.app_operation.forms import PaymentForm
from apps.app_operation.models.operation import Operation
from farm.shortcuts import get_object_or_404


class _TransactionRecordView(View):
    """Shared plumbing for recording payment/repayment transactions."""

    def _render_transaction_form(
        self, operation, form, template, remaining_balance, source_entity
    ):
        """Render a payment/repayment form with the shared transaction context."""
        return render(
            self.request,
            template,
            {
                "form": form,
                "operation": operation,
                "remaining_balance": remaining_balance,
                "source_entity": source_entity,
                "source_balance": source_entity.balance if source_entity else None,
                "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
            },
        )

    def _process_transaction(
        self, operation, create_transaction, label, use_form_error
    ):
        """
        Bind and validate the ``PaymentForm``, create the transaction via
        *create_transaction* and handle the success/error flow.

        Returns ``(response, form)`` — *response* is a redirect on success, otherwise
        ``None`` and *form* carries any errors for re-rendering. ``label`` drives the
        log/audit wording ("payment" / "repayment"); ``use_form_error`` selects
        ``form.add_error`` (repayment) vs ``messages.error`` (payment) on failure.
        """
        request = self.request
        logger.debug(
            f"Processing {label} transaction | operation_pk={operation.pk} | "
            f"user={request.user.username}"
        )
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                officer = request.user
                amount = form.cleaned_data["amount"]
                logger.debug(
                    f"Creating {label} transaction | amount={amount} | "
                    f"date={form.cleaned_data['date']}"
                )

                with db_transaction.atomic():
                    create_transaction(
                        amount=amount,
                        officer=officer,
                        date=form.cleaned_data["date"],
                        note=form.cleaned_data["note"],
                    )
                    logger.debug(
                        f"{label.capitalize()} transaction created | "
                        f"operation_id={operation.pk} | amount={amount}"
                    )
                    audit_logger.info(
                        f"{label}_transaction_created | Transaction:{operation.pk} | "
                        f"user={request.user.username} | operation_id={operation.pk} | "
                        f"amount={amount}"
                    )
                messages.success(
                    request,
                    f"{label.capitalize()} of {amount} recorded for Operation #{operation.pk}.",
                )
                return redirect("operation_detail_view", pk=operation.pk), form
            except Exception as e:
                logger.exception(f"{label} transaction creation failed")
                error_details = build_error_details(
                    e, extra={"operation_id": operation.pk}
                )
                logger.error(
                    f"{label.capitalize()} transaction creation failed | "
                    f"exception_type={error_details['exception_type']} | "
                    f"error_message={error_details['error_message']} | "
                    f"operation_id={operation.pk}"
                )
                audit_logger.error(
                    f"{label}_transaction_failed | Transaction:{operation.pk} | "
                    f"user={request.user.username} | error={error_details}"
                )
                if use_form_error:
                    form.add_error("amount", str(e))
                else:
                    messages.error(request, f"Error: {str(e)}")
        else:
            error_details = {"form_errors": str(form.errors)}
            logger.warning(f"{label} form validation failed | {error_details}")
            audit_logger.info(
                f"{label}_form_validation_failed | Transaction:{operation.pk} | "
                f"user={request.user.username} | {error_details}"
            )
        # Form errors will be displayed in template
        return None, form


class RecordTransactionPaymentView(_TransactionRecordView):
    """Record a payment transaction for an operation."""

    def _setup(self, pk):
        """Load + cast the operation. Returns ``(operation, response)``."""
        logger.debug(
            f"Fetching operation for payment | operation_pk={pk} | "
            f"user={self.request.user.username}"
        )
        operation = get_object_or_404(
            Operation, pk=pk, error_message="Operation not found or has been deleted."
        )
        operation = Operation.objects.cast(operation)
        logger.debug(
            f"Operation loaded | operation_id={operation.pk} | "
            f"operation_type={operation.operation_type} | "
            f"remaining_to_settle={operation.amount_remaining_to_settle}"
        )
        return operation, None

    def get(self, request, *args, **kwargs):
        operation, response = self._setup(kwargs["pk"])
        if response is not None:
            return response
        assert operation is not None

        form = PaymentForm(
            initial={
                "date": timezone.now().date(),
            }
        )

        # The payment transaction debits the operation's payment source fund.
        return self._render_transaction_form(
            operation,
            form,
            "app_operation/add_payment_form.html",
            operation.amount_remaining_to_settle,
            getattr(operation, "payment_source_fund", None),
        )

    def post(self, request, *args, **kwargs):
        operation, response = self._setup(kwargs["pk"])
        if response is not None:
            return response
        assert operation is not None

        response, form = self._process_transaction(
            operation,
            create_transaction=operation.create_payment_transaction,
            label="payment",
            use_form_error=False,
        )
        if response is not None:
            return response

        # The payment transaction debits the operation's payment source fund.
        return self._render_transaction_form(
            operation,
            form,
            "app_operation/add_payment_form.html",
            operation.amount_remaining_to_settle,
            getattr(operation, "payment_source_fund", None),
        )


class RecordTransactionRepaymentView(_TransactionRecordView):
    """Record a repayment transaction for an operation."""

    def _setup(self, pk):
        """Load + cast the operation. Returns ``(operation, remaining_amount, response)``."""
        logger.debug(
            f"Fetching operation for repayment | operation_pk={pk} | "
            f"user={self.request.user.username}"
        )
        operation = Operation.objects.filter(pk=pk).first()
        if not operation:
            logger.error(f"Operation not found | operation_pk={pk}")
            audit_logger.info(
                f"repayment_operation_not_found | Operation:None | "
                f"user={self.request.user.username} | operation_pk={pk}"
            )
            return None, None, HttpResponseNotFound("No Operation matches the provided info")

        # Cast to correct proxy so amount_remaining_to_repay is available
        operation = Operation.objects.cast(operation)
        logger.debug(
            f"Operation loaded | operation_id={operation.pk} | "
            f"operation_type={operation.operation_type}"
        )

        if not operation.can_repay:
            error_msg = (
                f"This operation does not accept repayments: {operation.operation_type}"
            )
            logger.warning(
                f"Operation does not accept repayments | "
                f"operation_type={operation.operation_type}"
            )
            audit_logger.info(
                f"repayment_not_accepted | Operation:{operation.pk} | "
                f"user={self.request.user.username} | operation_type={operation.operation_type}"
            )
            return None, None, HttpResponseBadRequest(error_msg)

        remaining_amount = operation.amount_remaining_to_repay
        return operation, remaining_amount, None

    def get(self, request, *args, **kwargs):
        operation, remaining_amount, response = self._setup(kwargs["pk"])
        if response is not None:
            return response
        assert operation is not None
        assert remaining_amount is not None

        form = PaymentForm(
            initial={
                "date": timezone.now().date(),
            }
        )

        # The repayment transaction is sourced from the payment target fund (the
        # entity that pays the money back).
        return self._render_transaction_form(
            operation,
            form,
            "app_operation/add_repayment_form.html",
            remaining_amount,
            getattr(operation, "payment_target_fund", None),
        )

    def post(self, request, *args, **kwargs):
        operation, remaining_amount, response = self._setup(kwargs["pk"])
        if response is not None:
            return response
        assert operation is not None
        assert remaining_amount is not None

        response, form = self._process_transaction(
            operation,
            create_transaction=operation.create_repayment_transaction,
            label="repayment",
            use_form_error=True,
        )
        if response is not None:
            return response

        # The repayment transaction is sourced from the payment target fund (the
        # entity that pays the money back).
        return self._render_transaction_form(
            operation,
            form,
            "app_operation/add_repayment_form.html",
            remaining_amount,
            getattr(operation, "payment_target_fund", None),
        )
