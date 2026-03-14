from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from apps.app_entity.models import Entity
from apps.app_personal_operation.models import Operation

# def cash_list_view(request, person_pk):
#     # Ensure the entity is an internal person
#     person = get_object_or_404(
#         Entity, pk=person_pk, is_internal=True, person__isnull=False
#     )

#     # Injections: Money coming from World to Person
#     injections = Operation.objects.filter(
#         source=person
#     )  # person.operations_incoming.all().select_related("source", "officer")

#     world = Entity.objects.get(is_world=True)
#     # Withdrawals: Money going from Person to World (if you use the same model)
#     # Or if you have a separate Withdrawal model, fetch it here.
#     withdrawals = person.operations_outgoing.filter(destination=world)

#     context = {
#         "person": person,
#         "injections": injections,
#         "withdrawals": withdrawals,
#     }
#     return render(
#         request, "app_personal_operation/cash_injection/cash_list.html", context
#     )


def operation_list_view(request, person_pk):
    # 1. Resolve the Person
    entity_person = get_object_or_404(
        Entity, pk=person_pk, is_internal=True, person__isnull=False
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
    return render(request, "app_personal_operation/generic_cash_list.html", context)
