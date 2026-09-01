from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from apps.app_base.logging_utils import audit_logger, logger
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity, EntityType
from apps.app_entity.forms import ProjectForm


def project_edit_view(request, pk):
    """Edit an existing Project entity."""
    logger.debug(f"Fetching project entity | entity_pk={pk}")
    entity = get_object_or_404(
        Entity,
        pk=pk,
        error_message="Project not found or has been deleted."
    )
    logger.debug(
        f"Entity loaded | entity_id={entity.id} | entity_name={entity.name} | "
        f"entity_type={entity.entity_type}"
    )

    if entity.entity_type != EntityType.PROJECT:
        error_msg = f"Entity {entity.id} is not a Project (type: {entity.entity_type})"
        logger.warning(error_msg)
        audit_logger.info(
            f"invalid_entity_type_for_project_edit | Entity:{entity.id} | "
            f"user={request.user.username} | actual_type={entity.entity_type} | "
            f"expected_type=PROJECT"
        )
        messages.error(request, "This entity is not a Project.")
        return redirect("entity_list")

    if request.method == "POST":
        logger.debug(
            f"Processing project update | entity_id={entity.id} | "
            f"user={request.user.username}"
        )
        form = ProjectForm(request.POST, instance=entity)
        logger.debug(
            f"ProjectForm instantiated with POST data for update | "
            f"fields_submitted={list(request.POST.keys())}"
        )

        if form.is_valid():
            logger.debug("Form validation passed")
            try:
                with transaction.atomic():
                    form.save()
                    logger.debug(
                        f"Project updated successfully | entity_id={entity.id} | "
                        f"entity_name={entity.name}"
                    )
                    audit_logger.info(
                        f"project_updated | Entity:{entity.id} | "
                        f"user={request.user.username} | name={entity.name}"
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
                logger.error(
                    f"Project update failed | "
                    f"exception_type={error_details['exception_type']} | "
                    f"error_message={error_details['error_message']} | "
                    f"entity_id={entity.id}"
                )
                audit_logger.error(
                    f"project_update_failed | Entity:{entity.id} | "
                    f"user={request.user.username} | error={error_details}"
                )
                messages.error(request, f"Update failed: {str(e)}")
        else:
            error_details = {
                "field_errors": {f: list(msgs) for f, msgs in form.errors.items()},
                "entity_id": entity.id,
                "fields_submitted": list(request.POST.keys()),
            }
            logger.warning(f"Form validation failed | {error_details}")
            audit_logger.info(
                f"project_form_validation_failed | Entity:{entity.id} | "
                f"user={request.user.username} | {error_details}"
            )
    else:
        logger.debug(
            f"GET request - initializing project form for editing | "
            f"entity_id={entity.id} | entity_name={entity.name}"
        )
        form = ProjectForm(instance=entity)

    context = {"form": form, "entity": entity, "is_edit": True}
    return render(request, "app_entity/project_form.html", context)
