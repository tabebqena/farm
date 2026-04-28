from django.db.models import Q
from django.shortcuts import render

from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity
from apps.app_operation.models.operation import Operation
from apps.app_operation.models.proxies import PROXY_MAP


def operation_list_view(request, person_pk):
    # 1. Resolve the Person
    entity_person = get_object_or_404(
        Entity,
        pk=person_pk,
        error_message="Entity not found or has been deleted."
    )

    # 2. Fetch all operations where the person is involved
    all_operations = (
        Operation.objects.filter(Q(source=entity_person) | Q(destination=entity_person))
        .order_by("-date", "-created_at")
    )

    # 3. Cast to proxy classes
    operations = [
        PROXY_MAP.get(op.operation_type, Operation).objects.get(pk=op.pk)
        for op in all_operations
    ]

    context = {
        "entity_person": entity_person,
        "operations": operations,
    }
    return render(request, "app_operation/operation_list.html", context)
