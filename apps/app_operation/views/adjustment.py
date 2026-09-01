from decimal import Decimal

from django import forms
from django.contrib import messages
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.app_adjustment.forms import AccountingAdjustmentForm
from apps.app_adjustment.models import (
    Adjustment,
    AdjustmentType,
    InvoiceItemAdjustment,
)
from apps.app_inventory.stock import active_lines_for_item
from apps.app_base.logging_utils import audit_logger, logger
from apps.app_base.reversal import request_reversal, reversal_guard_error
from apps.app_operation.models import Operation


def _build_adjustment_type_data():
    """Build a JSON-safe mapping of adjustment type values to their metadata."""
    return {
        t.value: {
            "label": str(t.label),
            "is_reduction": AdjustmentType.is_reduction(t.value),
        }
        for t in AdjustmentType
        if not AdjustmentType.is_item_correction(t.value)
    }


def parse_item_changes(post, items):
    """
    Parse the per-item ``item_<pk>_new_quantity`` / ``item_<pk>_new_unit_price``
    POST fields into a list of changed-item dicts.

    Each returned dict has ``item``, ``new_quantity`` and ``new_unit_price``
    (either may be ``None`` when only the other field changed). Raises
    ``ValueError`` with a translated message on the first invalid value.
    """
    changed_items_data = []
    for item in items:
        new_qty_str = post.get(f"item_{item.pk}_new_quantity", "").strip()
        new_price_str = post.get(f"item_{item.pk}_new_unit_price", "").strip()

        new_qty = None
        new_price = None

        if new_qty_str:
            try:
                new_qty = Decimal(new_qty_str)
            except Exception:
                raise ValueError(
                    _("Invalid quantity for {}.").format(item.product_template.name)
                )

        if new_price_str:
            try:
                new_price = Decimal(new_price_str)
            except Exception:
                raise ValueError(
                    _("Invalid price for {}.").format(item.product_template.name)
                )

        if new_qty is not None or new_price is not None:
            changed_items_data.append(
                {
                    "item": item,
                    "new_quantity": new_qty,
                    "new_unit_price": new_price,
                }
            )
    return changed_items_data


def record_accounting_adjustment(request, pk):
    """Record a simple accounting adjustment on a PURCHASE, SALE, or EXPENSE operation."""
    operation: Operation = get_object_or_404(Operation, pk=pk)
    # Cast so proxy attributes (e.g. period_entity for the closed-period
    # guard) are resolved from the concrete operation type.
    operation = Operation.objects.cast(operation)

    # Guards: operation type and reversal status
    if not operation.can_adjust:
        messages.warning(
            request, _("This operation type does not support adjustments.")
        )
        return redirect("operation_detail_view", pk=pk)

    if operation.is_reversed or operation.is_reversal:
        messages.warning(
            request,
            _("Cannot adjust a reversed or reversal operation."),
        )
        return redirect("operation_detail_view", pk=pk)

    # Build adjustment type metadata for the template (json_script filter serializes it)
    adjustment_type_data = _build_adjustment_type_data()
    prior_adjustments_net = str(operation.effective_amount - operation.amount)

    if request.method == "GET":
        form = AccountingAdjustmentForm(
            initial={"date": timezone.now().date()},
            operation_type=operation.operation_type,
        )
        context = {
            "form": form,
            "operation": operation,
            "adjustment_type_data": adjustment_type_data,
            "prior_adjustments_net": prior_adjustments_net,
        }
        return render(request, "app_adjustment/record_adjustment.html", context)

    # POST
    form = AccountingAdjustmentForm(
        request.POST, operation_type=operation.operation_type
    )

    if not form.is_valid():
        context = {
            "form": form,
            "operation": operation,
            "adjustment_type_data": adjustment_type_data,
            "prior_adjustments_net": prior_adjustments_net,
        }
        messages.error(request, _("Please correct the errors below."))
        return render(request, "app_adjustment/record_adjustment.html", context)

    try:
        # Reject adjustments dated inside a closed financial period.
        from apps.app_operation.models.period import is_date_in_closed_period

        if is_date_in_closed_period(
            operation.period_entity, form.cleaned_data["date"]
        ):
            raise forms.ValidationError(
                _("Cannot record an adjustment dated within a closed financial period.")
            )

        # Create and save the adjustment
        adj = Adjustment(
            operation=operation,
            type=form.cleaned_data["type"],
            amount=form.cleaned_data["amount"],
            reason=form.cleaned_data.get("reason", ""),
            date=form.cleaned_data["date"],
            officer=request.user,
        )
        adj.full_clean()
        adj.save()

        amount = form.cleaned_data["amount"]
        messages.success(
            request,
            _("Adjustment of ${} recorded successfully.").format(amount),
        )
        return redirect("operation_detail_view", pk=pk)

    except Exception as e:
        messages.error(request, _("Error: {}").format(str(e)))
        form = AccountingAdjustmentForm(
            request.POST, operation_type=operation.operation_type
        )
        context = {
            "form": form,
            "operation": operation,
            "adjustment_type_data": adjustment_type_data,
            "prior_adjustments_net": prior_adjustments_net,
        }
        return render(request, "app_adjustment/record_adjustment.html", context)


def record_item_adjustment(request, pk):
    """Record an invoice item adjustment (by modifying item qty/price) on PURCHASE or SALE."""
    operation = get_object_or_404(Operation, pk=pk)
    operation = operation.cast()

    # Guards: operation type, is_items_adjustable, and reversal status
    if not operation.is_items_adjustable:
        messages.warning(
            request,
            _(
                "Invoice item adjustments are only allowed on Purchase or Sale operations with invoice items."
            ),
        )
        return redirect("operation_detail_view", pk=pk)

    if operation.is_reversed or operation.is_reversal:
        messages.warning(
            request,
            _("Cannot adjust a reversed or reversal operation."),
        )
        return redirect("operation_detail_view", pk=pk)

    items = list(operation.items.all())
    for item in items:
        # Spec VA3: expose the already-moved quantity so the form can floor
        # the New Qty input and show it to the officer.
        item.moved_qty = (
            active_lines_for_item(item).aggregate(total=Sum("quantity"))["total"]
            or Decimal("0")
        )

    if request.method == "GET":
        context = {
            "operation": operation,
            "items": items,
            "today": timezone.now().date(),
        }
        return render(request, "app_adjustment/record_item_adjustment.html", context)

    # POST: parse per-item changes and create InvoiceItemAdjustment
    date = request.POST.get("date")
    reason = request.POST.get("reason", "")

    # Validate date
    try:
        from django.forms.fields import DateField as DjangoDateField

        date_field = DjangoDateField()
        date = date_field.clean(date)
    except forms.ValidationError as e:
        messages.error(request, _("Invalid date: {}").format(str(e)))
        context = {
            "operation": operation,
            "items": items,
            "today": timezone.now().date(),
        }
        return render(request, "app_adjustment/record_item_adjustment.html", context)

    # Reject adjustments dated inside a closed financial period.
    from apps.app_operation.models.period import is_date_in_closed_period

    if is_date_in_closed_period(operation.period_entity, date):
        messages.error(
            request,
            _("Cannot record an item adjustment dated within a closed financial period."),
        )
        context = {
            "operation": operation,
            "items": items,
            "today": timezone.now().date(),
        }
        return render(request, "app_adjustment/record_item_adjustment.html", context)

    # Parse the per-item changes from the POST fields
    try:
        changed_items_data = parse_item_changes(request.POST, items)
    except ValueError as e:
        messages.error(request, str(e))
        context = {
            "operation": operation,
            "items": items,
            "today": timezone.now().date(),
        }
        return render(request, "app_adjustment/record_item_adjustment.html", context)

    # Validate at least one item changed
    if not changed_items_data:
        messages.error(request, _("No items were modified."))
        context = {
            "operation": operation,
            "items": items,
            "today": timezone.now().date(),
        }
        return render(request, "app_adjustment/record_item_adjustment.html", context)

    try:
        with db_transaction.atomic():
            # Creation + finalization of the adjustment and its lines live on
            # the model so the view only parses the request.
            InvoiceItemAdjustment.create_from_item_changes(
                operation=operation,
                changed_items_data=changed_items_data,
                reason=reason,
                date=date,
                officer=request.user,
            )

        messages.success(
            request,
            _("Invoice item adjustment recorded successfully."),
        )
        return redirect("operation_detail_view", pk=pk)

    except Exception as e:
        messages.error(request, _("Error: {}").format(str(e)))
        context = {
            "operation": operation,
            "items": items,
            "today": timezone.now().date(),
        }
        return render(request, "app_adjustment/record_item_adjustment.html", context)


def reverse_adjustment(request, adjustment_id):
    """Reverse an accounting adjustment."""
    adjustment = get_object_or_404(Adjustment, pk=adjustment_id)
    operation = adjustment.operation

    logger.debug(
        f"Fetching adjustment for reversal | adjustment_pk={adjustment_id} | "
        f"operation_pk={operation.pk} | user={request.user.username}"
    )
    logger.debug(
        f"Adjustment loaded | adjustment_id={adjustment.pk} | type={adjustment.type} | "
        f"amount={float(adjustment.amount)}"
    )

    # Safety checks
    error_msg = reversal_guard_error(adjustment, "adjustment")
    if error_msg:
        logger.warning(f"{error_msg} | adjustment_id={adjustment.pk}")
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    if operation.is_reversed or operation.is_reversal:
        error_msg = _(
            "Cannot reverse an adjustment on a reversed or reversal operation."
        )
        logger.warning(f"{error_msg} | operation_id={operation.pk}")
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    officer = request.user

    if request.method == "POST":
        logger.debug(
            f"Processing adjustment reversal | adjustment_id={adjustment.pk} | "
            f"officer={officer.username}"
        )
        response = request_reversal(
            request,
            adjustment,
            record_type="adjustment",
            reverse_call=lambda officer, reason: adjustment.reverse(
                officer=officer,
                date=timezone.now().date(),
                reason=reason,
            ),
            audit_success=lambda request, obj, reason, reversal: (
                f"adjustment_reversed | Adjustment:{obj.pk} | "
                f"user={request.user.username} | type={obj.type} | "
                f"amount={float(obj.amount)} | reason={reason} | "
                f"officer={request.user.username}"
            ),
            audit_failure=lambda request, obj, error, error_details: (
                f"adjustment_reversal_failed | Adjustment:{obj.pk} | "
                f"user={request.user.username} | error={error_details}"
            ),
            success_message=lambda request, obj, reason: (
                _(
                    "Adjustment and its linked invoice item adjustment reversed successfully."
                )
                if getattr(obj, "item_adjustment", None) is not None
                else _("Adjustment reversed successfully.")
            ),
            error_message=lambda error: _("Reversal failed: {}").format(str(error)),
            redirect_to=lambda obj: redirect(
                "operation_detail_view", pk=obj.operation_id
            ),
            error_details_extra=lambda obj: {"adjustment_id": obj.pk},
        )
        if response is not None:
            return response

    context = {
        "adjustment": adjustment,
        "operation": operation,
    }
    return render(request, "app_adjustment/reverse_adjustment.html", context)


def reverse_item_adjustment(request, item_adjustment_id):
    """Reverse an invoice item adjustment."""
    item_adjustment = get_object_or_404(InvoiceItemAdjustment, pk=item_adjustment_id)
    operation = item_adjustment.operation

    logger.debug(
        f"Fetching item adjustment for reversal | item_adjustment_pk={item_adjustment_id} | "
        f"operation_pk={operation.pk} | user={request.user.username}"
    )
    logger.debug(
        f"Item adjustment loaded | item_adjustment_id={item_adjustment.pk} | "
        f"type={item_adjustment.type}"
    )

    # Safety checks
    error_msg = reversal_guard_error(item_adjustment, "item_adjustment")
    if error_msg:
        logger.warning(f"{error_msg} | item_adjustment_id={item_adjustment.pk}")
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    if operation.is_reversed or operation.is_reversal:
        error_msg = _(
            "Cannot reverse an item adjustment on a reversed or reversal operation."
        )
        logger.warning(f"{error_msg} | operation_id={operation.pk}")
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    officer = request.user

    if request.method == "POST":
        logger.debug(
            f"Processing item adjustment reversal | "
            f"item_adjustment_id={item_adjustment.pk} | officer={officer.username}"
        )
        response = request_reversal(
            request,
            item_adjustment,
            record_type="item_adjustment",
            reverse_call=lambda officer, reason: item_adjustment.reverse(
                officer=officer,
                date=timezone.now().date(),
                reason=reason,
            ),
            audit_success=lambda request, obj, reason, reversal: (
                f"item_adjustment_reversed | InvoiceItemAdjustment:{obj.pk} | "
                f"user={request.user.username} | type={obj.type} | "
                f"reason={reason} | officer={request.user.username}"
            ),
            audit_failure=lambda request, obj, error, error_details: (
                f"item_adjustment_reversal_failed | "
                f"InvoiceItemAdjustment:{obj.pk} | "
                f"user={request.user.username} | error={error_details}"
            ),
            success_message=lambda request, obj, reason: _(
                "Item adjustment reversed successfully."
            ),
            error_message=lambda error: _("Reversal failed: {}").format(str(error)),
            redirect_to=lambda obj: redirect(
                "operation_detail_view", pk=obj.operation_id
            ),
            error_details_extra=lambda obj: {"item_adjustment_id": obj.pk},
        )
        if response is not None:
            return response

    context = {
        "item_adjustment": item_adjustment,
        "operation": operation,
    }
    return render(request, "app_adjustment/reverse_item_adjustment.html", context)
