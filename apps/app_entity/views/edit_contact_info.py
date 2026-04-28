from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from farm.shortcuts import get_object_or_404
from apps.app_entity.models import ContactInfo, Entity


def edit_contact_info_view(request, pk):
    # Fetch the specific contact record
    contact = get_object_or_404(
        ContactInfo,
        pk=pk,
        error_message="Contact information not found or has been deleted."
    )
    entity = contact.entity

    if request.method == "POST":
        label = request.POST.get("label")
        value = request.POST.get("value")
        is_primary = request.POST.get("is_primary") == "on"

        try:
            with transaction.atomic():
                # If this contact is being set to primary, demote others of the SAME entity
                if is_primary:
                    entity.contacts.filter(is_primary=True).update(is_primary=False)

                # Update the allowed fields
                contact.label = label
                contact.value = value
                contact.is_primary = is_primary
                contact.save()

            messages.success(
                request, f"Success: {contact.get_label_display()} contact updated."
            )
            return redirect("entity_detail", pk=entity.id)
        except Exception as e:
            messages.error(request, f"Update Error: {str(e)}")

    context = {
        "contact": contact,
        "entity": entity,
        "type_choices": ContactInfo.TYPES,
        "label_choices": ContactInfo.LabelTypes,
        "is_edit": True,
    }
    return render(request, "app_entity/contact_form.html", context)
