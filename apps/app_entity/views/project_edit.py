from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity, EntityType
from apps.app_entity.forms import ProjectForm


@debug_view
def project_edit_view(request, pk):
    """Edit an existing Project entity."""
    with DebugContext.section("Fetching project entity", {"entity_pk": pk}):
        entity = get_object_or_404(
            Entity,
            pk=pk,
            error_message="Project not found or has been deleted."
        )
        DebugContext.success("Entity loaded", {
            "entity_id": entity.id,
            "entity_name": entity.name,
            "entity_type": entity.entity_type,
        })

    if entity.entity_type != EntityType.PROJECT:
        error_msg = f"Entity {entity.id} is not a Project (type: {entity.entity_type})"
        DebugContext.warn(error_msg)
        DebugContext.audit(
            action="invalid_entity_type_for_project_edit",
            entity_type="Entity",
            entity_id=entity.id,
            details={"actual_type": entity.entity_type, "expected_type": "PROJECT"},
            user=request.user.username
        )
        messages.error(request, "This entity is not a Project.")
        return redirect("entity_list")

    if request.method == "POST":
        with DebugContext.section("Processing project update", {
            "entity_id": entity.id,
            "user": request.user.username,
        }):
            form = ProjectForm(request.POST, instance=entity)
            DebugContext.log("ProjectForm instantiated with POST data for update", {
                "fields_submitted": list(request.POST.keys()),
            })

            if form.is_valid():
                DebugContext.success("Form validation passed")
                try:
                    with DebugContext.section("Saving project entity"):
                        with transaction.atomic():
                            form.save()
                            DebugContext.success("Project updated successfully", {
                                "entity_id": entity.id,
                                "entity_name": entity.name,
                            })
                            DebugContext.audit(
                                action="project_updated",
                                entity_type="Entity",
                                entity_id=entity.id,
                                details={"name": entity.name},
                                user=request.user.username
                            )
                            messages.success(
                                request, f"Project '{entity.name}' updated successfully."
                            )
                            return redirect("entity_detail", pk=entity.pk)
                except Exception as e:
                    error_details = {
                        "exception_type": type(e).__name__,
                        "error_message": str(e),
                        "entity_id": entity.id,
                        "user": request.user.username,
                    }
                    DebugContext.error("Project update failed", e, data=error_details)
                    DebugContext.audit(
                        action="project_update_failed",
                        entity_type="Entity",
                        entity_id=entity.id,
                        details=error_details,
                        user=request.user.username
                    )
                    messages.error(request, f"Update failed: {str(e)}")
            else:
                error_details = {
                    "field_errors": {f: list(msgs) for f, msgs in form.errors.items()},
                    "entity_id": entity.id,
                    "fields_submitted": list(request.POST.keys()),
                }
                DebugContext.warn("Form validation failed", error_details)
                DebugContext.audit(
                    action="project_form_validation_failed",
                    entity_type="Entity",
                    entity_id=entity.id,
                    details=error_details,
                    user=request.user.username
                )
    else:
        DebugContext.log("GET request - initializing project form for editing", {
            "entity_id": entity.id,
            "entity_name": entity.name,
        })
        form = ProjectForm(instance=entity)

    context = {"form": form, "entity": entity, "is_edit": True}
    return render(request, "app_entity/project_form.html", context)
