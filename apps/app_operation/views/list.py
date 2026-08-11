from decimal import Decimal

from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity
from apps.app_operation.models.operation import Operation
from apps.app_operation.models.proxies import PROXY_MAP


@debug_view
def operation_list_view(request, person_pk):
    """List all operations involving a person."""
    with DebugContext.section("Fetching entity for operation listing", {
        "entity_pk": person_pk,
        "user": request.user.username,
    }):
        entity_person = get_object_or_404(
            Entity,
            pk=person_pk,
            error_message="Entity not found or has been deleted."
        )
        DebugContext.success("Entity loaded", {
            "entity_id": entity_person.id,
            "entity_name": entity_person.name,
        })

    with DebugContext.section("Fetching operations involving entity", {
        "entity_id": entity_person.id,
    }):
        all_operations = (
            Operation.objects.filter(Q(source=entity_person) | Q(destination=entity_person))
            .order_by("-date", "-created_at")
        )
        DebugContext.log("Operations query executed", {
            "count": all_operations.count(),
        })

        proxy_operations = [
            PROXY_MAP.get(op.operation_type, Operation).objects.get(pk=op.pk)
            for op in all_operations
        ]
        DebugContext.success("Operations loaded", {
            "count": len(proxy_operations),
            "entity_id": entity_person.id,
        })

    # Precompute user-friendly settlement values for the list template.
    # Operations fall into three kinds with different settlement semantics:
    #   one_shot  - settled in full at creation (cash flows, funding, capital,
    #               corrections, birth/death/consumption, internal transfers).
    #   paid      - settled over time via payments (purchase, sale, expense).
    #   repayed   - recovered over time via repayments (loan, worker advance).
    operations = []
    for op in proxy_operations:
        total = op.effective_amount or Decimal("0.00")

        if op.has_repayment:
            kind = "repayed"
            paid = op.amount_repayed or Decimal("0.00")
            remaining = op.amount_remaining_to_repay or Decimal("0.00")
            fully_settled = bool(op.is_fully_repayed)
        elif op.is_partially_payable:
            kind = "paid"
            paid = op.amount_settled or Decimal("0.00")
            remaining = op.amount_remaining_to_settle or Decimal("0.00")
            fully_settled = bool(op.is_fully_settled)
        else:
            # One-shot operations settle fully at creation (reversal voids it).
            kind = "one_shot"
            paid = op.amount_settled or total
            remaining = Decimal("0.00")
            fully_settled = bool(op.is_fully_settled)

        if remaining < Decimal("0.00"):
            remaining = Decimal("0.00")

        percent = 0
        if total > Decimal("0.00"):
            percent = min(int(round(float(paid) / float(total) * 100)), 100)

        operations.append({
            "operation": op,
            "kind": kind,
            "paid": paid,
            "remaining": remaining,
            "total": total,
            "fully_settled": fully_settled,
            "percent": percent,
        })

    paginator = Paginator(operations, 25)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Replace the ambiguous "Entity" navigation label with the entity's display name
    if entity_person.entity_type in ("system", "world"):
        request.navigation_overrides = {"related_urls": {"Entity": None}}
    else:
        request.navigation_overrides = {
            "related_urls": {
                "Entity": {
                    "title": entity_person.get_display_name(),
                    "url": reverse(
                        "entity_detail", kwargs={"pk": entity_person.pk}
                    ),
                },
            }
        }

    context = {
        "entity_person": entity_person,
        "operations": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "balance": entity_person.balance,
        "currency": getattr(settings, "CURRENCY_SYMBOL", "$"),
    }
    return render(request, "app_operation/operation_list.html", context)
