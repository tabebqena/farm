from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.app_base.debug import DebugContext, debug_view
from apps.app_entity.models import Entity, EntityType
from apps.app_entity.forms import ProjectForm


@debug_view
def project_create_view(request):
    """Create a new Project entity."""
    if request.method == "POST":
        with DebugContext.section("Processing project creation request", {
            "user": request.user.username,
            "method": "POST",
        }):
            form = ProjectForm(request.POST)
            DebugContext.log("ProjectForm instantiated with POST data", {
                "fields_submitted": list(request.POST.keys()),
            })

            if form.is_valid():
                DebugContext.success("Form validation passed")
                try:
                    with DebugContext.section("Creating project entity and associated fund"):
                        with transaction.atomic():
                            entity = Entity.create(
                                entity_type=EntityType.PROJECT,
                                **form.cleaned_data,
                            )
                            DebugContext.success("Project created successfully", {
                                "entity_id": entity.id,
                                "entity_name": entity.name,
                                "fund_id": entity.id,
                            })
                            DebugContext.audit(
                                action="project_created",
                                entity_type="Entity",
                                entity_id=entity.id,
                                details={
                                    "name": entity.name,
                                    "entity_type": "PROJECT",
                                    "fund_initialized": True,
                                },
                                user=request.user.username
                            )
                            messages.success(
                                request,
                                _("Project '%(name)s' initialized with Fund ID #%(fund_id)s")
                                % {"name": entity.name, "fund_id": entity.id},
                            )
                            return redirect("entity_detail", pk=entity.pk)

                except Exception as e:
                    error_details = {
                        "exception_type": type(e).__name__,
                        "error_message": str(e),
                        "user": request.user.username,
                    }
                    DebugContext.error("Project creation failed", e, data=error_details)
                    DebugContext.audit(
                        action="project_creation_failed",
                        entity_type="Entity",
                        entity_id=None,
                        details=error_details,
                        user=request.user.username
                    )
                    messages.error(
                        request,
                        _("Failed to initialize project: %(error)s") % {"error": str(e)},
                    )
            else:
                error_details = {
                    "field_errors": {f: list(msgs) for f, msgs in form.errors.items()},
                    "fields_submitted": list(request.POST.keys()),
                }
                DebugContext.warn("Form validation failed", error_details)
                DebugContext.audit(
                    action="project_form_validation_failed",
                    entity_type="Entity",
                    entity_id=None,
                    details=error_details,
                    user=request.user.username
                )
    else:
        DebugContext.log("GET request - initializing empty project form")
        form = ProjectForm()

    return render(request, "app_entity/project_form.html", context={"form": form})
