from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.app_entity.models import Entity, EntityType


def project_create_view(request):
    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description", "")
        end_date = request.POST.get("end_date") or None
        feasibility_file = request.FILES.get("feasibility_study")

        is_vendor = request.POST.get("is_vendor") == "on"
        is_client = request.POST.get("is_client") == "on"

        try:
            with transaction.atomic():
                entity = Entity.create(
                    entity_type=EntityType.PROJECT,
                    name=name,
                    description=description,
                    feasibility_study=feasibility_file,
                    end_date=end_date,
                    is_vendor=is_vendor,
                    is_client=is_client,
                )
                messages.success(
                    request,
                    _("Project '%(name)s' initialized with Fund ID #%(fund_id)s")
                    % {"name": entity.name, "fund_id": entity.id},
                )
                return redirect("entity_detail", pk=entity.pk)

        except Exception as e:
            messages.error(
                request,
                _("Failed to initialize project: %(error)s") % {"error": str(e)},
            )

    return render(request, "app_entity/project_form.html")
