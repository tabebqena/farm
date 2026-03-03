from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_entity.models import Entity


def project_edit_view(request, pk):
    # Fetch the Entity and follow the relation to the Project
    entity = get_object_or_404(Entity.objects.select_related("project"), pk=pk)
    project = entity.project

    if not project:
        messages.error(request, "This entity is not a Project.")
        return redirect("entity_list")

    if request.method == "POST":
        # 1. Update Project Identity
        project.name = request.POST.get("name")
        project.description = request.POST.get("description", "")

        # 2. Update Entity Configuration Flags
        entity.is_internal = request.POST.get("is_internal") == "on"
        entity.active = request.POST.get("active") == "on"
        entity.can_pay = request.POST.get("can_pay") == "on"

        # Project-specific roles (usually projects are clients or internal)
        entity.is_client = request.POST.get("is_client") == "on"
        entity.is_vendor = request.POST.get("is_vendor") == "on"

        try:
            with transaction.atomic():
                project.save()
                entity.save()
                messages.success(
                    request, f"Project '{project.name}' updated successfully."
                )
                return redirect("entity_detail", pk=entity.pk)
        except Exception as e:
            messages.error(request, f"Update failed: {str(e)}")

    context = {"entity": entity, "project": project, "is_edit": True}
    return render(request, "app_entity/project_form.html", context)
