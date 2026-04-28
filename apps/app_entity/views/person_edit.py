from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity, EntityType
from apps.app_entity.forms import PersonForm


@debug_view
def person_edit_view(request, pk):
    """Edit an existing Person entity."""
    with DebugContext.section("Fetching person entity", {"entity_pk": pk}):
        entity = get_object_or_404(
            Entity,
            pk=pk,
            error_message="Person not found or has been deleted."
        )
        DebugContext.success("Entity loaded", {
            "entity_id": entity.id,
            "entity_name": entity.name,
            "entity_type": entity.entity_type,
        })

    if entity.entity_type != EntityType.PERSON:
        error_msg = f"Entity {entity.id} is not a Person (type: {entity.entity_type})"
        DebugContext.warn(error_msg)
        DebugContext.audit(
            action="invalid_entity_type_for_person_edit",
            entity_type="Entity",
            entity_id=entity.id,
            details={"actual_type": entity.entity_type, "expected_type": "PERSON"},
            user=request.user.username
        )
        messages.error(request, "This entity is not a Person.")
        return redirect("entity_list")

    if request.method == "POST":
        with DebugContext.section("Processing person update", {
            "entity_id": entity.id,
            "user": request.user.username,
        }):
            form = PersonForm(request.POST, instance=entity)
            DebugContext.log("PersonForm instantiated with POST data for update", {
                "fields_submitted": list(request.POST.keys()),
            })

            if form.is_valid():
                DebugContext.success("Form validation passed")
                try:
                    with DebugContext.section("Saving person entity"):
                        with transaction.atomic():
                            form.save()
                            DebugContext.success("Person updated successfully", {
                                "entity_id": entity.id,
                                "entity_name": entity.name,
                            })
                            DebugContext.audit(
                                action="person_updated",
                                entity_type="Entity",
                                entity_id=entity.id,
                                details={"name": entity.name},
                                user=request.user.username
                            )
                            messages.success(
                                request, f"Identity for {entity.name} updated successfully."
                            )
                            return redirect("entity_detail", pk=entity.pk)
                except Exception as e:
                    error_details = {
                        "exception_type": type(e).__name__,
                        "error_message": str(e),
                        "entity_id": entity.id,
                        "user": request.user.username,
                    }
                    DebugContext.error("Person update failed", e, data=error_details)
                    DebugContext.audit(
                        action="person_update_failed",
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
                    action="person_form_validation_failed",
                    entity_type="Entity",
                    entity_id=entity.id,
                    details=error_details,
                    user=request.user.username
                )
    else:
        DebugContext.log("GET request - initializing person form for editing", {
            "entity_id": entity.id,
            "entity_name": entity.name,
        })
        form = PersonForm(instance=entity)

    context = {"form": form, "entity": entity, "is_edit": True}
    return render(request, "app_entity/person_form.html", context)
