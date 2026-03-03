from django.shortcuts import render, get_object_or_404, redirect
from django.db import transaction
from django.contrib import messages
from apps.app_entity.models import Entity, ContactInfo


def add_contact_info_view(request, entity_id):
    entity = get_object_or_404(Entity, pk=entity_id)

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
                f"Success: Added {label} {contact_type} for {entity.get_display_name()}",
            )
            return redirect("entity_detail", pk=entity.id)
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    context = {
        "entity": entity,
        "type_choices": ContactInfo.TYPES,
        "label_choices": ContactInfo.LabelTypes,
    }
    return render(request, "app_entity/contact_form.html", context)
