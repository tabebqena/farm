from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views import View

from apps.app_base.logging_utils import audit_logger, logger
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import ContactInfo, Entity


class EditContactInfoView(View):
    """Edit contact information."""

    def _setup(self, pk):
        """Load the contact and its entity. Returns ``(contact, entity, response)``."""
        logger.debug(f"Fetching contact information | contact_pk={pk}")
        contact = get_object_or_404(
            ContactInfo,
            pk=pk,
            error_message="Contact information not found or has been deleted.",
        )
        entity = contact.entity
        logger.debug(
            f"Contact loaded | contact_id={contact.id} | entity_id={entity.id} | "
            f"contact_type={contact.contact_type}"
        )
        return contact, entity, None

    def get(self, request, *args, **kwargs):
        contact, entity, response = self._setup(kwargs["pk"])
        if response is not None:
            return response
        context = {
            "contact": contact,
            "entity": entity,
            "type_choices": ContactInfo.TYPES,
            "label_choices": ContactInfo.LabelTypes,
            "is_edit": True,
        }
        return render(request, "app_entity/contact_form.html", context)

    def post(self, request, *args, **kwargs):
        contact, entity, response = self._setup(kwargs["pk"])
        if response is not None:
            return response
        logger.debug(
            f"Processing contact information update | contact_id={contact.id} | "
            f"entity_id={entity.id} | user={request.user.username}"
        )
        label = request.POST.get("label")
        value = request.POST.get("value")
        is_primary = request.POST.get("is_primary") == "on"

        logger.debug(
            f"Contact form data extracted | label={label} | is_primary={is_primary} | "
            f"value_length={len(str(value)) if value else 0}"
        )

        try:
            with transaction.atomic():
                if is_primary:
                    logger.debug(f"Demoting existing primary contacts for entity | entity_id={entity.id}")
                    primaries = entity.contacts.filter(is_primary=True).all()
                    for p in primaries:
                        p.is_primary = False
                        p.save()
                contact.label = label
                contact.value = value
                contact.is_primary = is_primary
                contact.save()

            logger.debug(
                f"Contact information updated | contact_id={contact.id} | "
                f"is_primary={is_primary}"
            )
            audit_logger.info(
                f"contact_info_updated | ContactInfo:{contact.id} | "
                f"user={request.user.username} | entity_id={entity.id} | "
                f"label={label} | is_primary={is_primary}"
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
            logger.error(
                f"Contact update failed | "
                f"exception_type={error_details['exception_type']} | "
                f"error_message={error_details['error_message']} | "
                f"contact_id={contact.id}"
            )
            audit_logger.error(
                f"contact_info_update_failed | ContactInfo:{contact.id} | "
                f"user={request.user.username} | error={error_details}"
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
