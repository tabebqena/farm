from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import ContactInfo, Entity


@debug_view
def edit_contact_info_view(request, pk):
    """Edit contact information."""
    with DebugContext.section("Fetching contact information", {"contact_pk": pk}):
        contact = get_object_or_404(
            ContactInfo,
            pk=pk,
            error_message="Contact information not found or has been deleted."
        )
        entity = contact.entity
        DebugContext.success("Contact loaded", {
            "contact_id": contact.id,
            "entity_id": entity.id,
            "contact_type": contact.contact_type,
        })

    if request.method == "POST":
        with DebugContext.section("Processing contact information update", {
            "contact_id": contact.id,
            "entity_id": entity.id,
            "user": request.user.username,
        }):
            label = request.POST.get("label")
            value = request.POST.get("value")
            is_primary = request.POST.get("is_primary") == "on"

            DebugContext.log("Contact form data extracted", {
                "label": label,
                "is_primary": is_primary,
                "value_length": len(str(value)) if value else 0,
            })

            try:
                with DebugContext.section("Saving contact info changes"):
                    with transaction.atomic():
                        if is_primary:
                            DebugContext.log("Demoting existing primary contacts for entity", {
                                "entity_id": entity.id,
                            })
                            entity.contacts.filter(is_primary=True).update(is_primary=False)

                        contact.label = label
                        contact.value = value
                        contact.is_primary = is_primary
                        contact.save()

                DebugContext.success("Contact information updated", {
                    "contact_id": contact.id,
                    "is_primary": is_primary,
                })
                DebugContext.audit(
                    action="contact_info_updated",
                    entity_type="ContactInfo",
                    entity_id=contact.id,
                    details={
                        "entity_id": entity.id,
                        "label": label,
                        "is_primary": is_primary,
                    },
                    user=request.user.username
                )

                messages.success(
                    request, f"Success: {contact.get_label_display()} contact updated."
                )
                return redirect("entity_detail", pk=entity.id)
            except Exception as e:
                error_details = {
                    "exception_type": type(e).__name__,
                    "error_message": str(e),
                    "contact_id": contact.id,
                    "entity_id": entity.id,
                    "user": request.user.username,
                }
                DebugContext.error("Contact update failed", e, data=error_details)
                DebugContext.audit(
                    action="contact_info_update_failed",
                    entity_type="ContactInfo",
                    entity_id=contact.id,
                    details=error_details,
                    user=request.user.username
                )
                messages.error(request, f"Update Error: {str(e)}")

    context = {
        "contact": contact,
        "entity": entity,
        "type_choices": ContactInfo.TYPES,
        "label_choices": ContactInfo.LabelTypes,
        "is_edit": True,
    }
    return render(request, "app_entity/contact_form.html", context)
