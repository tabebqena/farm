"""Operation detail view.

:class:`OperationDetailView` renders a single operation with its navigation
overrides (edit / reverse links etc.).
"""

from django.conf import settings
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View

from apps.app_base.logging_utils import logger
from apps.app_operation.models import Operation
from farm.shortcuts import get_object_or_404


def _build_navigation_overrides(operation):
    """Build navigation related-url overrides for the operation detail page.

    Replaces the generic "Source Entity"/"Destination Entity" labels with the
    real entity names, and adds an operations-list link for each real
    (non-virtual) counterpart entity. ``None`` drops a related link entirely
    (system/world entities have no detail page). Returns an empty dict when
    nothing should be overridden.
    """
    related_url_overrides = {}
    for label, entity in (
        ("Source Entity", operation.source),
        ("Destination Entity", operation.destination),
    ):
        if entity.entity_type not in ("system", "world"):
            related_url_overrides[label] = {
                "title": entity.get_display_name(),
                "url": reverse("entity_detail", kwargs={"pk": entity.pk}),
            }
        else:
            related_url_overrides[label] = None

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
    return navigation_overrides


class OperationDetailView(View):
    """Display operation details with all related transactions and items."""

    def _items_and_valuations(self, operation):
        """Fetch invoice items (+ movement data) and capital valuations.

        Returns ``(items, items_data, capital_valuations)``.
        """
        items = operation.items.all() if type(operation).has_invoice else None
        logger.debug(
            f"Invoice items fetched | count={len(items) if items else 0} | "
            f"has_invoice={type(operation).has_invoice} | operation_id={operation.pk}"
        )

        capital_valuations = None
        if type(operation).has_capital_valuation:
            capital_valuations = operation.capital_valuations.select_related(
                "product", "product__product_template", "officer"
            )
            logger.debug(
                f"Capital valuations fetched | count={len(capital_valuations)} | "
                f"operation_id={operation.pk}"
            )

        logger.debug(
            f"Computing items_data for invoice items | operation_id={operation.pk} | "
            f"has_invoice={type(operation).has_invoice}"
        )
        items_data = operation.get_items_data()
        logger.debug(
            f"Items data computed | items_count={len(items_data)} | operation_id={operation.pk}"
        )
        return items, items_data, capital_valuations

    def _adjustments(self, operation):
        """Fetch the active accounting + item adjustments for the operation."""
        adjustments = list(
            operation.adjustments.filter(reversal_of__isnull=True).order_by("date")
        )
        item_adjustments = list(
            operation.item_adjustments.filter(reversal_of__isnull=True).order_by("date")
        )
        return adjustments, item_adjustments

    def _payment_balance(self, operation):
        """Compute the settlement/payment-balance summary for the operation.

        Returns a dict with ``has_settlement`` and the payment_balance
        components (paid, outstanding, net adjustment, overpayment,
        over-repayment).
        """
        logger.debug(f"Computing payment balance | operation_id={operation.pk}")
        # The non-accounting operations (Birth / Death / Consumption / Capital
        # Gain / Capital Loss) do not track settlement — they are fully settled
        # at their amount. Only accounting operations expose the settlement
        # mixin members, so guard has_settlement here (it is reused below for
        # the payment-transaction and one-shot flags).
        has_settlement = hasattr(operation, "amount_settled")

        payment_balance = operation.payment_balance()
        result = {
            "has_settlement": has_settlement,
            "paid_amount": payment_balance["paid_amount"],
            "outstanding_balance": payment_balance["outstanding_balance"],
            "net_adjustment": payment_balance["net_adjustment"],
            "overpayment_amount": payment_balance["overpayment_amount"],
            "over_repayment_amount": payment_balance["over_repayment_amount"],
        }
        logger.debug(
            f"Payment balance computed | {payment_balance} | operation_id={operation.pk}"
        )
        return result

    def get(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        logger.debug(
            f"Fetching operation details | operation_pk={pk} | user={request.user.username}"
        )
        operation = get_object_or_404(
            Operation, pk=pk, error_message="Operation not found or has been deleted."
        )
        operation = Operation.objects.cast(operation)
        logger.debug(
            f"Operation loaded | operation_id={operation.pk} | "
            f"operation_type={operation.operation_type} | is_reversed={operation.is_reversed}"
        )

        logger.debug(f"Fetching related transactions and items | operation_id={operation.pk}")
        transactions = operation.get_all_transactions()
        logger.debug(
            f"Transactions fetched | count={len(transactions)} | operation_id={operation.pk}"
        )

        items, items_data, capital_valuations = self._items_and_valuations(operation)
        adjustments, item_adjustments = self._adjustments(operation)

        payment = self._payment_balance(operation)
        has_settlement = payment["has_settlement"]
        paid_amount = payment["paid_amount"]
        outstanding_balance = payment["outstanding_balance"]
        net_adjustment = payment["net_adjustment"]
        overpayment_amount = payment["overpayment_amount"]
        over_repayment_amount = payment["over_repayment_amount"]

        # Set navigation overrides for entity detail links (see
        # _build_navigation_overrides): real entity names + an operations-list link.
        navigation_overrides = _build_navigation_overrides(operation)
        if navigation_overrides:
            request.navigation_overrides = navigation_overrides

        context = {
            "operation": operation,
            "transactions": transactions,
            "payment_transactions": (
                operation.payment_transactions
                if has_settlement
                else operation.get_all_transactions().none()
            ),
            "items": items,
            "items_data": items_data,
            "capital_valuations": capital_valuations,
            "has_capital_valuation": type(operation).has_capital_valuation,
            "adjustments": adjustments,
            "item_adjustments": item_adjustments,
            "is_reversed": operation.is_reversed,
            # Non-accounting operations have no standalone pay/settle action — render
            # them as one-shot (settled at creation) so the payment UI is hidden.
            "is_one_shot_operation": operation.is_one_shot or not has_settlement,
            "paid_amount": paid_amount,
            "outstanding_balance": outstanding_balance,
            "net_adjustment": net_adjustment,
            "overpayment_amount": overpayment_amount,
            "repayment_transactions": (
                operation.repayment_transactions
                if getattr(operation, "has_repayment", False)
                else operation.get_all_transactions().none()
            ),
            "over_repayment_amount": over_repayment_amount,
            "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
        }
        return render(request, "app_operation/operation_detail.html", context)
