from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_entity.models import Entity, Stakeholder


def add_stakeholder_base(request, parent_entity_id, role_type):
    # Rule 1: Host must be internal
    parent = get_object_or_404(Entity, pk=parent_entity_id, is_internal=True)

    if request.method == "POST":
        target_id = request.POST.get("target_entity")
        target_entity = get_object_or_404(Entity, pk=target_id, active=True)

        # Rule 2: Validation based on role_type
        error_msg = None
        if role_type == "worker" and not target_entity.person:
            error_msg = "Only People can be assigned as Workers."
        elif role_type == "shareholder" and not target_entity.person:
            error_msg = "Only People can be assigned as Shareholders."
        elif role_type == "vendor" and not target_entity.is_vendor:
            error_msg = f"{target_entity} is not configured as a Vendor."
        elif role_type == "client" and not target_entity.is_client:
            error_msg = f"{target_entity} is not configured as a Client."

        if error_msg:
            messages.error(request, f"Configuration Error: {error_msg}")
        else:
            Stakeholder.objects.get_or_create(
                parent=parent,
                target=target_entity,
                role=role_type,
            )
            messages.success(
                request, f"Successfully added {role_type}: {target_entity}"
            )
            return redirect("entity_detail", pk=parent.id)

    # Filter available entities based on the role requirements
    if role_type == "worker":
        available = Entity.objects.filter(is_worker=True, active=True)
    elif role_type == "shareholder":
        available = Entity.objects.filter(is_shareholder=True, active=True)
    elif role_type == "vendor":
        available = Entity.objects.filter(is_vendor=True, active=True)
    elif role_type == "client":
        available = Entity.objects.filter(is_client=True, active=True)

    # Exclude the host itself
    available = available.exclude(id=parent.id)

    return render(
        request,
        "app_entity/stakeholder_form.html",
        {
            "project_entity": parent,
            "entities": available,
            "role_type": role_type,
            "role_name": role_type.capitalize(),
        },
    )


# The four specific views
def add_vendor_view(request, pk):
    return add_stakeholder_base(request, pk, "vendor")


def add_client_view(request, pk):
    return add_stakeholder_base(request, pk, "client")


def add_worker_view(request, pk):
    return add_stakeholder_base(request, pk, "worker")


def add_shareholder_view(request, pk):
    return add_stakeholder_base(request, pk, "shareholder")
