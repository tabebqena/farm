from django.shortcuts import render

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity


@debug_view
def entity_detail_view(request, pk):
    """Display entity detail page."""
    with DebugContext.section("Fetching entity details", {
        "entity_pk": pk,
        "user": request.user.username,
    }):
        entity = get_object_or_404(
            Entity,
            pk=pk,
            error_message="Entity not found or has been deleted."
        )
        DebugContext.success("Entity loaded", {
            "entity_id": entity.id,
            "entity_type": entity.entity_type,
            "entity_name": entity.name,
        })

    context = {
        "entity": entity,
    }

    return render(request, "app_entity/entity_detail.html", context)
