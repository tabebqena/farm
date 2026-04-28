from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from farm.shortcuts import get_object_or_404
from apps.app_entity.models import ContactInfo, Entity


def add_contact_info_view(request, entity_id):
    entity = get_object_or_404(
        Entity,
        pk=entity_id,
        error_message="Entity not found or has been deleted."
    )

    if request.method == "POST":
        contact_type = request.POST.get("contact_type")
        label = request.POST.get("label")
        value = request.POST.get("value")
        is_primary = request.POST.get("is_primary") == "on"

        try:
            with transaction.atomic():
                # If this is the new primary, demote existing primary contacts
                # if is_primary:
                #     entity.contacts.filter(is_primary=True).update(is_primary=False)

                ContactInfo.objects.create(
                    entity=entity,
                    contact_type=contact_type,
                    label=label,
                    value=value,
                    is_primary=is_primary,
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
            messages.error(request, _("Error: %(error)s") % {"error": str(e)})

    context = {
        "entity": entity,
        "type_choices": ContactInfo.TYPES,
        "label_choices": ContactInfo.LabelTypes,
    }
    return render(request, "app_entity/contact_form.html", context)
