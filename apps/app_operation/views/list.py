from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from apps.app_entity.models import Entity
from apps.app_operation.models.operation import Operation


def operation_list_view(request, person_pk):
    # 1. Resolve the Person
    # Now it can be project also
    entity_person = Entity.objects.get(pk=person_pk)
    print(entity_person)

    entity_person = get_object_or_404(
        Entity,
        pk=person_pk,
        # is_internal=True,
        # person__isnull=False
    )

    # 2. Fetch all operations where the person is involved
    # This covers Injections (Incoming) and Withdrawals/Funding (Outgoing)
    all_operations = (
        Operation.objects.filter(Q(source=entity_person) | Q(destination=entity_person))
        .select_related("source", "destination", "officer")
        .order_by("-date", "-created_at")
    )

    context = {
        "entity_person": entity_person,
        "operations": all_operations,
    }
    return render(request, "app_operation/operation_list.html", context)
