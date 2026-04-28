from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity, EntityType
from apps.app_entity.forms import PersonForm


def person_edit_view(request, pk):
    entity = get_object_or_404(
        Entity,
        pk=pk,
        error_message="Person not found or has been deleted."
    )

    if entity.entity_type != EntityType.PERSON:
        messages.error(request, "This entity is not a Person.")
        return redirect("entity_list")

    if request.method == "POST":
        form = PersonForm(request.POST, instance=entity)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    messages.success(
                        request, f"Identity for {entity.name} updated successfully."
                    )
                    return redirect("entity_detail", pk=entity.pk)
            except Exception as e:
                messages.error(request, f"Update failed: {str(e)}")
        # Form errors will be displayed in template
    else:
        form = PersonForm(instance=entity)

    context = {"form": form, "entity": entity, "is_edit": True}
    return render(request, "app_entity/person_form.html", context)
