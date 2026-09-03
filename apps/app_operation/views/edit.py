"""Operation editing view.

:class:`OperationUpdateView` allows editing a not-yet-finalized operation's
editable fields.
"""

from django.contrib import messages
from django.db import transaction as db_transaction
from django.shortcuts import redirect, render
from django.views import View

from apps.app_base.logging_utils import audit_logger, build_error_details, logger
from farm.shortcuts import get_object_or_404
from apps.app_operation.models.operation import Operation
from apps.app_operation.models.proxies import PROXY_MAP


class OperationUpdateView(View):
    """Update non-financial fields of an operation."""

    def _setup(self, pk):
        """Load + guard the operation. Returns ``(operation, response)``."""
        logger.debug(
            f"Fetching operation for update | operation_pk={pk} | "
            f"user={self.request.user.username}"
        )
        operation = get_object_or_404(
            Operation,
            pk=pk,
            error_message="Operation not found or has been deleted."
        )
        operation = Operation.objects.cast(operation)
        logger.debug(
            f"Operation loaded | operation_id={operation.pk} | "
            f"operation_type={operation.operation_type} | is_reversed={operation.is_reversed}"
        )

        # Financial Protection: Do not allow editing reversed operations
        if operation.is_reversed:
            error_msg = "Cannot edit a reversed operation."
            logger.warning(f"{error_msg} | operation_id={operation.pk}")
            audit_logger.info(
                f"operation_update_attempt_on_reversed | Operation:{operation.pk} | "
                f"user={self.request.user.username} | reason=operation_already_reversed"
            )
            messages.error(self.request, error_msg)
            return None, redirect("operation_detail_view", pk=operation.pk)

        return operation, None

    def get(self, request, *args, **kwargs):
        """Render the operation edit form."""
        operation, response = self._setup(kwargs["pk"])
        if response is not None:
            return response
        assert operation is not None

        context = {
            "operation": operation,
            "config": PROXY_MAP.get(operation.operation_type),
            "is_update": True,
        }
        return render(request, "app_operation/generic_edit_form.html", context)

    def post(self, request, *args, **kwargs):
        """Update the operation's non-financial fields from the form."""
        operation, response = self._setup(kwargs["pk"])
        if response is not None:
            return response
        assert operation is not None

        logger.debug(
            f"Processing operation update | operation_pk={operation.pk} | "
            f"user={request.user.username}"
        )
        try:
            with db_transaction.atomic():
                # Strictly only update non-financial fields
                old_description = operation.description
                old_date = operation.date

                operation.description = request.POST.get("description", "")
                operation.date = request.POST.get("date")
                operation.save()  # Mixin will sync the date to linked transactions

                logger.debug(
                    f"Operation updated | operation_id={operation.pk} | "
                    f"old_description={old_description} | "
                    f"new_description={operation.description} | "
                    f"old_date={old_date} | new_date={operation.date}"
                )
                audit_logger.info(
                    f"operation_updated | Operation:{operation.pk} | "
                    f"user={request.user.username} | "
                    f"operation_type={operation.operation_type} | "
                    f"description_changed={old_description != operation.description} | "
                    f"date_changed={old_date != operation.date}"
                )

            messages.success(request, "Update saved successfully.")
            return redirect("operation_detail_view", pk=operation.pk)
        except Exception as e:
            error_details = build_error_details(
                e, extra={"operation_id": operation.pk}
            )
            logger.error(
                f"Operation update failed | exception_type={error_details['exception_type']} | "
                f"error_message={error_details['error_message']} | "
                f"operation_id={operation.pk}"
            )
            audit_logger.error(
                f"operation_update_failed | Operation:{operation.pk} | "
                f"user={request.user.username} | error={error_details}"
            )
            messages.error(request, f"Update Error: {str(e)}")

        context = {
            "operation": operation,
            "config": PROXY_MAP.get(operation.operation_type),
            "is_update": True,
        }
        return render(request, "app_operation/generic_edit_form.html", context)
