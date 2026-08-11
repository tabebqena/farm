from decimal import Decimal

from django.conf import settings
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.app_base.debug import DebugContext, debug_view
from apps.app_operation.models import Operation
from farm.shortcuts import get_object_or_404


@debug_view
def operation_detail_view(request, pk):
    """Display operation details with all related transactions and items."""
    with DebugContext.section(
        "Fetching operation details",
        {
            "operation_pk": pk,
            "user": request.user.username,
        },
    ):
        operation = get_object_or_404(
            Operation, pk=pk, error_message="Operation not found or has been deleted."
        )
        operation = Operation.objects.cast(operation)
        DebugContext.success(
            "Operation loaded",
            {
                "operation_id": operation.pk,
                "operation_type": operation.operation_type,
                "is_reversed": operation.is_reversed,
            },
        )

    with DebugContext.section(
        "Fetching related transactions and items",
        {
            "operation_id": operation.pk,
        },
    ):
        transactions = operation.get_all_transactions()
        DebugContext.log(
            "Transactions fetched",
            {
                "count": len(transactions),
                "operation_id": operation.pk,
            },
        )

        items = operation.items.all() if type(operation).has_invoice else None
        DebugContext.log(
            "Invoice items fetched",
            {
                "count": len(items) if items else 0,
                "has_invoice": type(operation).has_invoice,
                "operation_id": operation.pk,
            },
        )

        adjustments = list(
            operation.adjustments.filter(reversal_of__isnull=True).order_by("date")
        )
        item_adjustments = list(
            operation.item_adjustments.filter(reversal_of__isnull=True).order_by("date")
        )

    with DebugContext.section(
        "Computing items_data for invoice items",
        {
            "operation_id": operation.pk,
            "has_invoice": type(operation).has_invoice,
        },
    ):
        items_data = operation.get_items_data()
        DebugContext.log(
            "Items data computed",
            {
                "items_count": len(items_data),
                "operation_id": operation.pk,
            },
        )

    with DebugContext.section(
        "Computing payment balance",
        {
            "operation_id": operation.pk,
        },
    ):
        paid_amount = float(operation.amount_settled)
        outstanding_balance = float(operation.amount_remaining_to_settle)
        DebugContext.log(
            "Payment balance computed",
            {
                "paid_amount": paid_amount,
                "outstanding_balance": outstanding_balance,
                "operation_id": operation.pk,
            },
        )

        net_adjustment = float(
            (operation.effective_amount or Decimal("0.00")) - operation.amount
        )
        DebugContext.log(
            "Net adjustment computed",
            {
                "net_adjustment": net_adjustment,
                "operation_id": operation.pk,
            },
        )

        overpayment_amount = float(
            operation.amount_settled - operation.total_settlable_amount
            if operation.is_overpayed_settled
            else Decimal("0.00")
        )
        DebugContext.log(
            "Overpayment computed",
            {
                "overpayment_amount": overpayment_amount,
                "operation_id": operation.pk,
            },
        )

        over_repayment_amount = float(
            operation.amount_repayed - operation.total_repayable_amount
            if operation.is_overpaid_repayed
            else Decimal("0.00")
        )
        DebugContext.log(
            "Over-repayment computed",
            {
                "over_repayment_amount": over_repayment_amount,
                "operation_id": operation.pk,
            },
        )

    # Set navigation overrides for entity detail links.
    # Replace the generic "Source Entity"/"Destination Entity" labels with the
    # real entity names so the navigation is unambiguous. Long names are kept on
    # one line via CSS (fixed-width, ellipsis) in the navigation template.
    # A None value drops the related link entirely (system/world entities have
    # no detail page).
    related_url_overrides = {}
    if operation.source.entity_type not in ("system", "world"):
        related_url_overrides["Source Entity"] = {
            "title": operation.source.get_display_name(),
            "url": reverse("entity_detail", kwargs={"pk": operation.source.pk}),
        }
    else:
        related_url_overrides["Source Entity"] = None
    if operation.destination.entity_type not in ("system", "world"):
        related_url_overrides["Destination Entity"] = {
            "title": operation.destination.get_display_name(),
            "url": reverse("entity_detail", kwargs={"pk": operation.destination.pk}),
        }
    else:
        related_url_overrides["Destination Entity"] = None

    # Add an operations-list link for each real (non-virtual) counterpart entity
    # so the navigation bar always offers a way back to that entity's operation
    # history. System/World entities have no operations list, so they are exempt.
    add_related = []
    for entity in (operation.source, operation.destination):
        if entity.entity_type in ("system", "world"):
            continue
        add_related.append(
            {
                "title": _("Operations: %(name)s")
                % {"name": entity.get_display_name()},
                "url": reverse(
                    "operation_list_view", kwargs={"person_pk": entity.pk}
                ),
            }
        )

    navigation_overrides = {}
    if related_url_overrides:
        navigation_overrides["related_urls"] = related_url_overrides
    if add_related:
        navigation_overrides["add_related"] = add_related
    if navigation_overrides:
        request.navigation_overrides = navigation_overrides

    context = {
        "operation": operation,
        "transactions": transactions,
        "payment_transactions": operation.payment_transactions,
        "items": items,
        "items_data": items_data,
        "adjustments": adjustments,
        "item_adjustments": item_adjustments,
        "is_reversed": operation.is_reversed,
        "is_one_shot_operation": operation._is_one_shot_operation,
        "paid_amount": paid_amount,
        "outstanding_balance": outstanding_balance,
        "net_adjustment": net_adjustment,
        "overpayment_amount": overpayment_amount,
        "repayment_transactions": operation.repayment_transactions,
        "over_repayment_amount": over_repayment_amount,
        "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
    }
    return render(request, "app_operation/operation_detail.html", context)
