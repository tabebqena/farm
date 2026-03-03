from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_entity.models import Entity


def person_edit_view(request, pk):
    # We fetch by Entity PK because the Entity is the "central" object
    entity = get_object_or_404(Entity.objects.select_related("person"), pk=pk)
    person = entity.person

    if not person:
        messages.error(request, "This entity is not a Person.")
        return redirect("entity_list")

    if request.method == "POST":
        # 1. Capture Identity Data
        person.private_name = request.POST.get("private_name")
        person.private_description = request.POST.get("private_description", "")

        # 2. Capture Entity Role Flags
        entity.is_worker = request.POST.get("is_worker") == "on"
        entity.is_vendor = request.POST.get("is_vendor") == "on"
        entity.is_client = request.POST.get("is_client") == "on"
        entity.is_shareholder = request.POST.get("is_shareholder") == "on"
        entity.is_internal = request.POST.get("is_internal") == "on"
        entity.active = request.POST.get("active") == "on"
        entity.can_pay = request.POST.get("can_pay") == "on"

        try:
            with transaction.atomic():
                person.save()
                entity.save()
                messages.success(
                    request, f"Identity for {person.name} updated successfully."
                )
                return redirect("entity_detail", pk=entity.pk)
        except Exception as e:
            messages.error(request, f"Update failed: {str(e)}")

    context = {"entity": entity, "person": person, "is_edit": True}
    return render(request, "app_entity/person_form.html", context)
