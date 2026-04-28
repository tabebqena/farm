from django.contrib import messages
from django.shortcuts import redirect, render

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Stakeholder


@debug_view
def edit_stakeholder_view(request, pk):
    """Edit stakeholder relationship details."""
    with DebugContext.section("Fetching stakeholder relationship", {"stakeholder_pk": pk}):
        stakeholder = get_object_or_404(
            Stakeholder,
            pk=pk,
            error_message="Stakeholder relationship not found or has been deleted."
        )
        parent = stakeholder.parent
        DebugContext.success("Stakeholder loaded", {
            "stakeholder_id": stakeholder.id,
            "parent_id": parent.id,
            "target_id": stakeholder.target.id,
            "role": stakeholder.role,
        })

    if request.method == "POST":
        with DebugContext.section("Processing stakeholder update", {
            "stakeholder_id": stakeholder.id,
            "parent_id": parent.id,
            "user": request.user.username,
        }):
            notes = request.POST.get("notes", "")
            is_active = request.POST.get("active") == "on"

            DebugContext.log("Stakeholder form data extracted", {
                "has_notes": bool(notes),
                "is_active": is_active,
            })

            try:
                with DebugContext.section("Saving stakeholder changes"):
                    stakeholder.notes = notes
                    stakeholder.active = is_active
                    stakeholder.save()

                DebugContext.success("Stakeholder updated", {
                    "stakeholder_id": stakeholder.id,
                    "is_active": is_active,
                })
                DebugContext.audit(
                    action="stakeholder_updated",
                    entity_type="Stakeholder",
                    entity_id=stakeholder.id,
                    details={
                        "parent_id": parent.id,
                        "target_id": stakeholder.target.id,
                        "role": stakeholder.role,
                        "is_active": is_active,
                    },
                    user=request.user.username
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
                DebugContext.error("Stakeholder update failed", e, data=error_details)
                DebugContext.audit(
                    action="stakeholder_update_failed",
                    entity_type="Stakeholder",
                    entity_id=stakeholder.id,
                    details=error_details,
                    user=request.user.username
                )
                messages.error(request, f"Update Error: {str(e)}")

    context = {"stakeholder": stakeholder, "parent": parent, "is_edit": True}
    return render(request, "app_entity/stakeholder_form.html", context)
