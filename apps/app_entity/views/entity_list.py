from django.shortcuts import render

from apps.app_base.debug import DebugContext, debug_view
from apps.app_entity.models import Entity, EntityType

_VIRTUAL_TYPES = [EntityType.SYSTEM, EntityType.WORLD]


@debug_view
def entity_list_view(request):
    """List entities with filtering and search."""
    with DebugContext.section("Building entity list query", {
        "user": request.user.username,
    }):
        queryset = Entity.objects

        # Get Filter Params
        type_f = request.GET.get("type", "all")
        del_f = request.GET.get("deletion", "undeleted")
        act_f = request.GET.get("activation", "active")
        query = request.GET.get("q")

        filters_applied = {
            "type": type_f,
            "deletion": del_f,
            "activation": act_f,
            "search": query or "none",
        }
        DebugContext.log("Applying filters", filters_applied)

        # Filter by Type
        if type_f == "person":
            queryset = queryset.filter(entity_type=EntityType.PERSON)
        elif type_f == "project":
            queryset = queryset.filter(entity_type=EntityType.PROJECT)
        elif type_f == "system_world":
            queryset = queryset.filter(entity_type__in=_VIRTUAL_TYPES)
        else:
            queryset = queryset.exclude(entity_type__in=_VIRTUAL_TYPES)

        # Filter by Deletion
        if del_f == "deleted":
            queryset = queryset.filter(deleted_at__isnull=False)
        elif del_f == "undeleted":
            queryset = queryset.filter(deleted_at__isnull=True)

        # Filter by Activation
        if act_f == "active":
            queryset = queryset.filter(active=True)
        elif act_f == "inactive":
            queryset = queryset.filter(active=False)

        # Search
        if query:
            queryset = queryset.filter(name__icontains=query)

        result_count = queryset.count()
        DebugContext.success("Query executed", {"result_count": result_count})

    context = {
        "entities": queryset,
        "type_filter": type_f,
        "deletion_filter": del_f,
        "activation_filter": act_f,
        "search_query": query,
    }
    return render(request, "app_entity/entity_list.html", context)
