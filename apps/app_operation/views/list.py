from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.shortcuts import render

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

        operations = [
            PROXY_MAP.get(op.operation_type, Operation).objects.get(pk=op.pk)
            for op in all_operations
        ]
        DebugContext.success("Operations loaded", {
            "count": len(operations),
            "entity_id": entity_person.id,
        })

    paginator = Paginator(operations, 25)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "entity_person": entity_person,
        "operations": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
    }
    return render(request, "app_operation/operation_list.html", context)
