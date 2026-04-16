from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_entity.models import Entity, EntityType


def person_edit_view(request, pk):
    entity = get_object_or_404(Entity, pk=pk)

    if entity.entity_type != EntityType.PERSON:
        messages.error(request, "This entity is not a Person.")
        return redirect("entity_list")

    if request.method == "POST":
        entity.name = request.POST.get("name")
        entity.description = request.POST.get("private_description", "")
        entity.is_worker = request.POST.get("is_worker") == "on"
        entity.is_vendor = request.POST.get("is_vendor") == "on"
        entity.is_client = request.POST.get("is_client") == "on"
        entity.is_shareholder = request.POST.get("is_shareholder") == "on"
        entity.is_internal = request.POST.get("is_internal") == "on"
        entity.active = request.POST.get("active") == "on"
        entity.fund.active = request.POST.get("fund_active") == "on"

        try:
            with transaction.atomic():
                entity.fund.save()
                entity.save()
                messages.success(
                    request, f"Identity for {entity.name} updated successfully."
                )
                return redirect("entity_detail", pk=entity.pk)
        except Exception as e:
            messages.error(request, f"Update failed: {str(e)}")

    context = {"entity": entity, "is_edit": True}
    return render(request, "app_entity/person_form.html", context)
