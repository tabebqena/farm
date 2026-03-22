from django.db.models import Q
from django.shortcuts import render

from apps.app_entity.models import Entity


def entity_list_view(request):
    queryset = Entity.objects.select_related("person", "project")

    # 1. Get Filter Params
    type_f = request.GET.get("type", "all")
    del_f = request.GET.get("deletion", "undeleted")  # Default to undeleted
    act_f = request.GET.get("activation", "active")  # Default to active

    # 2. Filter by Type
    if type_f == "person":
        queryset = queryset.filter(person__isnull=False)
    elif type_f == "project":
        queryset = queryset.filter(project__isnull=False)
    elif type_f == "system_world":
        queryset = queryset.filter(Q(is_system=True) | Q(is_world=True))
    else:
        queryset = queryset.filter(Q(is_world=False) & Q(is_system=False))

    # 3. Filter by Deletion (Assuming is_deleted field exists)
    if del_f == "deleted":
        queryset = queryset.filter(deleted_at__isnull=False)
    elif del_f == "undeleted":
        queryset = queryset.filter(deleted_at__isnull=True)

    # 4. Filter by Activation
    if act_f == "active":
        queryset = queryset.filter(active=True)
    elif act_f == "inactive":
        queryset = queryset.filter(active=False)

    # 5. Search
    query = request.GET.get("q")
    if query:
        queryset = queryset.filter(
            Q(person__private_name__icontains=query) | Q(project__name__icontains=query)
        )

    context = {
        "entities": queryset,
        "type_filter": type_f,
        "deletion_filter": del_f,
        "activation_filter": act_f,
        "search_query": query,
    }
    return render(request, "app_entity/entity_list.html", context)
