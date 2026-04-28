from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from apps.app_entity.forms import PersonForm
from apps.app_entity.models import Entity, EntityType


def person_create_view(request):
    if request.method == "POST":
        form = PersonForm(request.POST)

        if form.is_valid():
            print(form.cleaned_data)
            try:
                with transaction.atomic():
                    # We continue to use Entity.create to ensure that the Fund
                    # and associated business logic are initialized correctly.
                    entity = Entity.create(
                        entity_type=EntityType.PERSON,
                        **form.cleaned_data,
                    )
                    messages.success(
                        request,
                        f"Person {entity.name} created with Fund ID #{entity.id}",
                    )
                    return redirect("entity_detail", pk=entity.pk)

            except Exception as e:
                messages.error(request, f"System Error: {str(e)}")
        else:
            print(form.errors)
    else:
        form = PersonForm()

    return render(
        request, "app_entity/person_form.html", context={"edit": False, "form": form}
    )
