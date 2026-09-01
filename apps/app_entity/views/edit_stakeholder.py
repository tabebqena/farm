from django.contrib import messages
from django.shortcuts import redirect, render

from apps.app_base.logging_utils import audit_logger, logger
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Stakeholder


def edit_stakeholder_view(request, pk):
    """Edit stakeholder relationship details."""
    logger.debug(f"Fetching stakeholder relationship | stakeholder_pk={pk}")
    stakeholder = get_object_or_404(
        Stakeholder,
        pk=pk,
        error_message="Stakeholder relationship not found or has been deleted."
    )
    parent = stakeholder.parent
    logger.debug(
        f"Stakeholder loaded | stakeholder_id={stakeholder.id} | "
        f"parent_id={parent.id} | target_id={stakeholder.target.id} | "
        f"role={stakeholder.role}"
    )

    if request.method == "POST":
        logger.debug(
            f"Processing stakeholder update | stakeholder_id={stakeholder.id} | "
            f"parent_id={parent.id} | user={request.user.username}"
        )
        notes = request.POST.get("notes", "")
        is_active = request.POST.get("active") == "on"

        logger.debug(
            f"Stakeholder form data extracted | has_notes={bool(notes)} | "
            f"is_active={is_active}"
        )

        try:
            stakeholder.notes = notes
            stakeholder.active = is_active
            stakeholder.save()

            logger.debug(
                f"Stakeholder updated | stakeholder_id={stakeholder.id} | "
                f"is_active={is_active}"
            )
            audit_logger.info(
                f"stakeholder_updated | Stakeholder:{stakeholder.id} | "
                f"user={request.user.username} | parent_id={parent.id} | "
                f"target_id={stakeholder.target.id} | role={stakeholder.role} | "
                f"is_active={is_active}"
            )

            messages.success(
                request,
                f"Stakeholder: Updated details for {stakeholder.target.get_display_name()}",
            )
            return redirect("entity_detail", pk=parent.id)
        except Exception as e:
            error_details = {
                "exception_type": type(e).__name__,
                "error_message": str(e),
                "stakeholder_id": stakeholder.id,
                "parent_id": parent.id,
                "user": request.user.username,
            }
            logger.error(
                f"Stakeholder update failed | "
                f"exception_type={error_details['exception_type']} | "
                f"error_message={error_details['error_message']} | "
                f"stakeholder_id={stakeholder.id}"
            )
            audit_logger.error(
                f"stakeholder_update_failed | Stakeholder:{stakeholder.id} | "
                f"user={request.user.username} | error={error_details}"
            )
            messages.error(request, f"Update Error: {str(e)}")

    context = {"stakeholder": stakeholder, "parent": parent, "is_edit": True}
    return render(request, "app_entity/stakeholder_form.html", context)
