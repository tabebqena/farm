from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.app_entity.models import Entity, Project


def project_create_view(request):
    if request.method == "POST":
        # 1. Extract Project Data
        name = request.POST.get("name")
        description = request.POST.get("description", "")
        end_date = request.POST.get("end_date")
        feasibility_file = request.FILES.get("feasibility_study")

        # 2. Extract Entity Role Flags
        is_vendor = request.POST.get("is_vendor") == "on"
        is_client = request.POST.get("is_client") == "on"

        try:
            with transaction.atomic():
                # 3. Create the Project instance
                project = Project(
                    name=name,
                    description=description,
                    feasibility_study=feasibility_file,
                )
                if end_date:
                    project.end_date = end_date
                project.save()

                # 4. Wrap it in an Entity (This triggers Fund creation)
                entity = Entity.create(
                    owner=project,
                    is_vendor=is_vendor,
                    is_client=is_client,
                    # Projects are usually not workers or shareholders
                    is_worker=False,
                    is_shareholder=False,
                    active=True,
                )

                messages.success(
                    request,
                    _("Project '%(name)s' initialized with Fund ID #%(fund_id)s")
                    % {"name": project.name, "fund_id": entity.fund.id},
                )
                return redirect("entity_detail", pk=entity.pk)

        except Exception as e:
            messages.error(
                request,
                _("Failed to initialize project: %(error)s") % {"error": str(e)},
            )

    return render(request, "app_entity/project_form.html")
