import traceback
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.app_adjustment.forms import AccountingAdjustmentForm
from apps.app_adjustment.models import (
    Adjustment,
    AdjustmentType,
    InvoiceItemAdjustment,
    InvoiceItemAdjustmentLine,
)
from apps.app_adjustment._item_type import InvoiceItemAdjustmentType
from apps.app_base.debug import DebugContext, debug_view
from apps.app_operation.models import Operation
from apps.app_operation.models.operation_type import OperationType


@debug_view
def record_accounting_adjustment(request, pk):
    """Record a simple accounting adjustment on a PURCHASE, SALE, or EXPENSE operation."""
    operation = get_object_or_404(Operation, pk=pk)

    # Cast to proxy to check operation-specific config
    proxy_operation = operation.cast()

    # Guards: operation type and reversal status
    if operation.operation_type not in (
        OperationType.PURCHASE,
        OperationType.SALE,
        OperationType.EXPENSE,
    ):
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

    if request.method == "GET":
        form = AccountingAdjustmentForm(
            initial={"date": timezone.now().date()},
            operation_type=operation.operation_type,
        )
        context = {"form": form, "operation": operation}
        return render(
            request, "app_adjustment/record_adjustment.html", context
        )

    # POST
    form = AccountingAdjustmentForm(
        request.POST, operation_type=operation.operation_type
    )

    if not form.is_valid():
        context = {"form": form, "operation": operation}
        messages.error(request, _("Please correct the errors below."))
        return render(
            request, "app_adjustment/record_adjustment.html", context
        )

    try:
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
        context = {"form": form, "operation": operation}
        return render(
            request, "app_adjustment/record_adjustment.html", context
        )


@debug_view
def record_item_adjustment(request, pk):
    """Record an invoice item adjustment (by modifying item qty/price) on PURCHASE or SALE."""
    operation = get_object_or_404(Operation, pk=pk)

    # Cast to proxy to check operation-specific config
    proxy_operation = operation.cast()

    # Guards: operation type and has_invoice
    if operation.operation_type not in (OperationType.PURCHASE, OperationType.SALE):
        messages.warning(
            request,
            _("Invoice item adjustments are only allowed on Purchase or Sale operations."),
        )
        return redirect("operation_detail_view", pk=pk)

    if not type(proxy_operation).has_invoice:
        messages.warning(
            request,
            _("This operation does not have invoice items."),
        )
        return redirect("operation_detail_view", pk=pk)

    if operation.is_reversed or operation.is_reversal:
        messages.warning(
            request,
            _("Cannot adjust a reversed or reversal operation."),
        )
        return redirect("operation_detail_view", pk=pk)

    items = operation.items.all()

    if request.method == "GET":
        context = {
            "operation": operation,
            "items": items,
            "today": timezone.now().date(),
        }
        return render(
            request, "app_adjustment/record_item_adjustment.html", context
        )

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
        return render(
            request, "app_adjustment/record_item_adjustment.html", context
        )

    # Collect changed items
    changed_items_data = []
    for item in items:
        new_qty_str = request.POST.get(f"item_{item.pk}_new_quantity", "").strip()
        new_price_str = request.POST.get(f"item_{item.pk}_new_unit_price", "").strip()
        is_removed_str = request.POST.get(f"item_{item.pk}_is_removed", "")

        is_removed = is_removed_str == "on"
        new_qty = None
        new_price = None

        # Parse quantity and price
        if new_qty_str:
            try:
                new_qty = Decimal(new_qty_str)
            except:
                messages.error(
                    request,
                    _("Invalid quantity for {}.").format(item.product.name),
                )
                context = {
                    "operation": operation,
                    "items": items,
                    "today": timezone.now().date(),
                }
                return render(
                    request, "app_adjustment/record_item_adjustment.html", context
                )

        if new_price_str:
            try:
                new_price = Decimal(new_price_str)
            except:
                messages.error(
                    request,
                    _("Invalid price for {}.").format(item.product.name),
                )
                context = {
                    "operation": operation,
                    "items": items,
                    "today": timezone.now().date(),
                }
                return render(
                    request, "app_adjustment/record_item_adjustment.html", context
                )

        # Check if anything changed
        if is_removed or new_qty is not None or new_price is not None:
            changed_items_data.append(
                {
                    "item": item,
                    "new_quantity": new_qty,
                    "new_unit_price": new_price,
                    "is_removed": is_removed,
                }
            )

    # Validate at least one item changed
    if not changed_items_data:
        messages.error(request, _("No items were modified."))
        context = {
            "operation": operation,
            "items": items,
            "today": timezone.now().date(),
        }
        return render(
            request, "app_adjustment/record_item_adjustment.html", context
        )

    # Determine the item adjustment type based on operation type
    if operation.operation_type == OperationType.PURCHASE:
        item_adj_type = InvoiceItemAdjustmentType.PURCHASE_ITEM_INCREASE
    else:  # SALE
        item_adj_type = InvoiceItemAdjustmentType.SALE_ITEM_INCREASE

    try:
        with db_transaction.atomic():
            # Create InvoiceItemAdjustment
            item_adj = InvoiceItemAdjustment(
                operation=operation,
                type=item_adj_type,
                reason=reason,
                date=date,
                officer=request.user,
            )
            item_adj.full_clean()
            item_adj.save()

            # Create InvoiceItemAdjustmentLine for each changed item
            for changed_item_data in changed_items_data:
                line = InvoiceItemAdjustmentLine(
                    adjustment=item_adj,
                    invoice_item=changed_item_data["item"],
                    new_quantity=changed_item_data["new_quantity"],
                    new_unit_price=changed_item_data["new_unit_price"],
                    is_removed=changed_item_data["is_removed"],
                )
                line.full_clean()
                line.save()

            # Finalize: creates the accounting Adjustment and transaction
            item_adj.finalize()

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
        return render(
            request, "app_adjustment/record_item_adjustment.html", context
        )


@debug_view
def reverse_adjustment(request, adjustment_id):
    """Reverse an accounting adjustment."""
    adjustment = get_object_or_404(Adjustment, pk=adjustment_id)
    operation = adjustment.operation

    with DebugContext.section("Fetching adjustment for reversal", {
        "adjustment_pk": adjustment_id,
        "operation_pk": operation.pk,
        "user": request.user.username,
    }):
        DebugContext.success("Adjustment loaded", {
            "adjustment_id": adjustment.pk,
            "type": adjustment.type,
            "amount": float(adjustment.amount),
        })

    # Safety checks
    if adjustment.is_reversed:
        error_msg = _("This adjustment has already been reversed.")
        DebugContext.warn(error_msg, {"adjustment_id": adjustment.pk})
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    if adjustment.is_reversal:
        error_msg = _("This adjustment is a reversal (you can't reverse it).")
        DebugContext.warn(error_msg, {"adjustment_id": adjustment.pk})
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    if operation.is_reversed or operation.is_reversal:
        error_msg = _("Cannot reverse an adjustment on a reversed or reversal operation.")
        DebugContext.warn(error_msg, {"operation_id": operation.pk})
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    officer = request.user

    if request.method == "POST":
        with DebugContext.section("Processing adjustment reversal", {
            "adjustment_id": adjustment.pk,
            "officer": officer.username,
        }):
            reason = request.POST.get("reversal_reason", "").strip()

            if not reason:
                error_msg = _("A reason for reversal is required.")
                DebugContext.warn(error_msg, {"adjustment_id": adjustment.pk})
                messages.error(request, error_msg)
            else:
                try:
                    with DebugContext.section("Executing adjustment reversal"):
                        adjustment.reverse(
                            officer=officer,
                            date=timezone.now().date(),
                            reason=reason,
                        )

                    DebugContext.success("Adjustment reversed successfully", {
                        "adjustment_id": adjustment.pk,
                        "type": adjustment.type,
                    })
                    DebugContext.audit(
                        action="adjustment_reversed",
                        entity_type="Adjustment",
                        entity_id=adjustment.pk,
                        details={
                            "type": adjustment.type,
                            "amount": float(adjustment.amount),
                            "reason": reason,
                            "officer": officer.username,
                        },
                        user=request.user.username
                    )

                    messages.success(
                        request, _("Adjustment reversed successfully.")
                    )
                    return redirect("operation_detail_view", pk=operation.pk)

                except Exception as e:
                    error_details = {
                        "exception_type": type(e).__name__,
                        "error_message": str(e),
                        "adjustment_id": adjustment.pk,
                        "officer": officer.username,
                        "traceback": traceback.format_exc(),
                    }
                    DebugContext.error("Adjustment reversal failed", e, data=error_details)
                    DebugContext.audit(
                        action="adjustment_reversal_failed",
                        entity_type="Adjustment",
                        entity_id=adjustment.pk,
                        details=error_details,
                        user=request.user.username
                    )
                    traceback.print_exc()
                    messages.error(request, _("Reversal failed: {}").format(str(e)))

    context = {
        "adjustment": adjustment,
        "operation": operation,
    }
    return render(request, "app_adjustment/reverse_adjustment.html", context)


@debug_view
def reverse_item_adjustment(request, item_adjustment_id):
    """Reverse an invoice item adjustment."""
    item_adjustment = get_object_or_404(InvoiceItemAdjustment, pk=item_adjustment_id)
    operation = item_adjustment.operation

    with DebugContext.section("Fetching item adjustment for reversal", {
        "item_adjustment_pk": item_adjustment_id,
        "operation_pk": operation.pk,
        "user": request.user.username,
    }):
        DebugContext.success("Item adjustment loaded", {
            "item_adjustment_id": item_adjustment.pk,
            "type": item_adjustment.type,
        })

    # Safety checks
    if item_adjustment.is_reversed:
        error_msg = _("This item adjustment has already been reversed.")
        DebugContext.warn(error_msg, {"item_adjustment_id": item_adjustment.pk})
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    if item_adjustment.is_reversal:
        error_msg = _("This item adjustment is a reversal (you can't reverse it).")
        DebugContext.warn(error_msg, {"item_adjustment_id": item_adjustment.pk})
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    if operation.is_reversed or operation.is_reversal:
        error_msg = _("Cannot reverse an item adjustment on a reversed or reversal operation.")
        DebugContext.warn(error_msg, {"operation_id": operation.pk})
        messages.warning(request, error_msg)
        return redirect("operation_detail_view", pk=operation.pk)

    officer = request.user

    if request.method == "POST":
        with DebugContext.section("Processing item adjustment reversal", {
            "item_adjustment_id": item_adjustment.pk,
            "officer": officer.username,
        }):
            reason = request.POST.get("reversal_reason", "").strip()

            if not reason:
                error_msg = _("A reason for reversal is required.")
                DebugContext.warn(error_msg, {"item_adjustment_id": item_adjustment.pk})
                messages.error(request, error_msg)
            else:
                try:
                    with DebugContext.section("Executing item adjustment reversal"):
                        item_adjustment.reverse(
                            officer=officer,
                            date=timezone.now().date(),
                            reason=reason,
                        )

                    DebugContext.success("Item adjustment reversed successfully", {
                        "item_adjustment_id": item_adjustment.pk,
                        "type": item_adjustment.type,
                    })
                    DebugContext.audit(
                        action="item_adjustment_reversed",
                        entity_type="InvoiceItemAdjustment",
                        entity_id=item_adjustment.pk,
                        details={
                            "type": item_adjustment.type,
                            "reason": reason,
                            "officer": officer.username,
                        },
                        user=request.user.username
                    )

                    messages.success(
                        request, _("Item adjustment reversed successfully.")
                    )
                    return redirect("operation_detail_view", pk=operation.pk)

                except Exception as e:
                    error_details = {
                        "exception_type": type(e).__name__,
                        "error_message": str(e),
                        "item_adjustment_id": item_adjustment.pk,
                        "officer": officer.username,
                        "traceback": traceback.format_exc(),
                    }
                    DebugContext.error("Item adjustment reversal failed", e, data=error_details)
                    DebugContext.audit(
                        action="item_adjustment_reversal_failed",
                        entity_type="InvoiceItemAdjustment",
                        entity_id=item_adjustment.pk,
                        details=error_details,
                        user=request.user.username
                    )
                    traceback.print_exc()
                    messages.error(request, _("Reversal failed: {}").format(str(e)))

    context = {
        "item_adjustment": item_adjustment,
        "operation": operation,
    }
    return render(request, "app_adjustment/reverse_item_adjustment.html", context)
