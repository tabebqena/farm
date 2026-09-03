"""View for adding contact information to an entity.

:class:`AddContactInfoView` lets the user attach a new contact record (phone,
email, etc.) to an existing entity.
"""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views import View

from apps.app_base.logging_utils import audit_logger, build_error_details, logger
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import ContactInfo, Entity


class AddContactInfoView(View):
    """Add contact information to an entity."""

    def _load_entity(self, entity_id):
        """Load the entity the new contact will be attached to."""
        logger.debug(f"Fetching entity for contact addition | entity_id={entity_id}")
        entity = get_object_or_404(
            Entity,
            pk=entity_id,
            error_message="Entity not found or has been deleted."
        )
        logger.debug(
            f"Entity loaded | entity_id={entity.id} | entity_name={entity.name}"
        )
        return entity

    def get(self, request, *args, **kwargs):
        """Render the contact-add form for an entity."""
        entity = self._load_entity(kwargs["entity_id"])
        context = {
            "entity": entity,
            "type_choices": ContactInfo.TYPES,
            "label_choices": ContactInfo.LabelTypes,
        }
        return render(request, "app_entity/contact_form.html", context)

    def post(self, request, *args, **kwargs):
        """Create a contact record from the submitted form data."""
        entity = self._load_entity(kwargs["entity_id"])
        logger.debug(
            f"Processing contact information addition | entity_id={entity.id} | "
            f"user={request.user.username}"
        )
        contact_type = request.POST.get("contact_type")
        label = request.POST.get("label")
        value = request.POST.get("value")
        is_primary = request.POST.get("is_primary") == "on"

        logger.debug(
            f"Contact form data extracted | contact_type={contact_type} | "
            f"label={label} | is_primary={is_primary} | "
            f"value_length={len(str(value)) if value else 0}"
        )

        try:
            with transaction.atomic():
                contact = ContactInfo.objects.create(
                    entity=entity,
                    contact_type=contact_type,
                    label=label,
                    value=value,
                    is_primary=is_primary,
                )

            logger.debug(
                f"Contact information created | contact_id={contact.id} | "
                f"entity_id={entity.id} | contact_type={contact_type}"
            )
            audit_logger.info(
                f"contact_info_added | ContactInfo:{contact.id} | "
                f"user={request.user.username} | entity_id={entity.id} | "
                f"contact_type={contact_type} | label={label} | "
                f"is_primary={is_primary}"
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
            error_details = build_error_details(
                e,
                extra={
                    "entity_id": entity.id,
                    "contact_type": contact_type,
                },
                user=request.user,
            )
            logger.error(
                f"Contact info creation failed | "
                f"exception_type={error_details['exception_type']} | "
                f"error_message={error_details['error_message']} | "
                f"entity_id={entity.id}"
            )
            audit_logger.error(
                f"contact_info_creation_failed | ContactInfo:None | "
                f"user={request.user.username} | error={error_details}"
            )
            messages.error(request, _("Error: %(error)s") % {"error": str(e)})

        context = {
            "entity": entity,
            "type_choices": ContactInfo.TYPES,
            "label_choices": ContactInfo.LabelTypes,
        }
        return render(request, "app_entity/contact_form.html", context)
