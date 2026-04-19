from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from apps.app_entity.models import Entity, EntityType


def person_create_view(request):
    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("private_description", "")

        config = {
            "is_vendor": request.POST.get("is_vendor") == "on",
            "is_client": request.POST.get("is_client") == "on",
            "is_worker": request.POST.get("is_worker") == "on",
            "is_shareholder": request.POST.get("is_shareholder") == "on",
            "is_internal": request.POST.get("is_internal") == "on",
        }

        try:
            with transaction.atomic():
                entity = Entity.create(
                    entity_type=EntityType.PERSON,
                    name=name,
                    description=description,
                    **config,
                )
                messages.success(
                    request,
                    f"Person {entity.name} created with Fund ID #{entity.id}",
                )
                return redirect("entity_detail", pk=entity.pk)

        except Exception as e:
            messages.error(request, f"System Error: {str(e)}")

    return render(request, "app_entity/person_form.html")
