from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import ContactInfo, Entity


@debug_view
def add_contact_info_view(request, entity_id):
    """Add contact information to an entity."""
    with DebugContext.section("Fetching entity for contact addition", {"entity_id": entity_id}):
        entity = get_object_or_404(
            Entity,
            pk=entity_id,
            error_message="Entity not found or has been deleted."
        )
        DebugContext.success("Entity loaded", {
            "entity_id": entity.id,
            "entity_name": entity.name,
        })

    if request.method == "POST":
        with DebugContext.section("Processing contact information addition", {
            "entity_id": entity.id,
            "user": request.user.username,
        }):
            contact_type = request.POST.get("contact_type")
            label = request.POST.get("label")
            value = request.POST.get("value")
            is_primary = request.POST.get("is_primary") == "on"

            DebugContext.log("Contact form data extracted", {
                "contact_type": contact_type,
                "label": label,
                "is_primary": is_primary,
                "value_length": len(str(value)) if value else 0,
            })

            try:
                with DebugContext.section("Creating contact info record"):
                    with transaction.atomic():
                        contact = ContactInfo.objects.create(
                            entity=entity,
                            contact_type=contact_type,
                            label=label,
                            value=value,
                            is_primary=is_primary,
                        )

                DebugContext.success("Contact information created", {
                    "contact_id": contact.id,
                    "entity_id": entity.id,
                    "contact_type": contact_type,
                })
                DebugContext.audit(
                    action="contact_info_added",
                    entity_type="ContactInfo",
                    entity_id=contact.id,
                    details={
                        "entity_id": entity.id,
                        "contact_type": contact_type,
                        "label": label,
                        "is_primary": is_primary,
                    },
                    user=request.user.username
                )

                messages.success(
                    request,
                    _("Success: Added %(label)s %(contact_type)s for %(entity)s")
                    % {
                        "label": label,
                        "contact_type": contact_type,
                        "entity": entity.get_display_name(),
                    },
                )
                return redirect("entity_detail", pk=entity.id)
            except Exception as e:
                error_details = {
                    "exception_type": type(e).__name__,
                    "error_message": str(e),
                    "entity_id": entity.id,
                    "contact_type": contact_type,
                    "user": request.user.username,
                }
                DebugContext.error("Contact info creation failed", e, data=error_details)
                DebugContext.audit(
                    action="contact_info_creation_failed",
                    entity_type="ContactInfo",
                    entity_id=None,
                    details=error_details,
                    user=request.user.username
                )
                messages.error(request, _("Error: %(error)s") % {"error": str(e)})

    context = {
        "entity": entity,
        "type_choices": ContactInfo.TYPES,
        "label_choices": ContactInfo.LabelTypes,
    }
    return render(request, "app_entity/contact_form.html", context)
