from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from apps.app_entity.models import Person


def person_create_view(request):
    if request.method == "POST":
        # 1. Identity Data
        p_name = request.POST.get("private_name")
        p_desc = request.POST.get("private_description", "")

        # 2. Entity Configuration Flags
        # checkbox 'on' becomes True, absence becomes False
        config = {
            "is_vendor": request.POST.get("is_vendor") == "on",
            "is_client": request.POST.get("is_client") == "on",
            "is_worker": request.POST.get("is_worker") == "on",
            "is_shareholder": request.POST.get("is_shareholder") == "on",
            "is_internal": request.POST.get("is_internal") == "on",
            "fund_active": request.POST.get("fund_active") == "on",
        }

        try:
            with transaction.atomic():
                # Step A: Create the Person
                person = Person.create(
                    private_name=p_name, private_description=p_desc, **config
                )

                messages.success(
                    request,
                    f"Person {person.name} created with Fund ID #{person.entity.fund.id}",
                )
                return redirect("entity_detail", pk=person.entity.pk)

        except Exception as e:
            messages.error(request, f"System Error: {str(e)}")

    return render(request, "app_entity/person_form.html")
