from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_entity.models import Stakeholder


def edit_stakeholder_view(request, pk):
    # Fetch the stakeholder relationship
    stakeholder = get_object_or_404(Stakeholder, pk=pk)
    parent = stakeholder.parent

    if request.method == "POST":
        # We only update mutable fields allowed by ImmutableMixin
        notes = request.POST.get("notes", "")
        is_active = request.POST.get("active") == "on"

        try:
            stakeholder.notes = notes
            stakeholder.active = is_active
            stakeholder.save()

            messages.success(
                request,
                f"Stakeholder: Updated details for {stakeholder.target.get_display_name()}",
            )
            return redirect("entity_detail", pk=parent.id)
        except Exception as e:
            messages.error(request, f"Update Error: {str(e)}")

    context = {"stakeholder": stakeholder, "parent": parent, "is_edit": True}
    return render(request, "app_entity/stakeholder_form.html", context)
