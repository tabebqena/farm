from decimal import Decimal
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_entity.models import Category, Entity


def category_create_view(request, parent_entity_id):
    # The Person or Project this category belongs to
    parent = get_object_or_404(Entity, id=parent_entity_id)
    print(parent.name, parent.project, parent.person)

    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description")
        raw_limit = request.POST.get("max_limit")
        max_limit = Decimal(raw_limit) if raw_limit else Decimal("0.00")

        config = {
            "is_vendor": False,
            "is_client": False,
            "is_worker": False,
            "is_shareholder": False,
            "is_internal": True,
            "can_pay": False,
        }

        try:
            with transaction.atomic():
                Category.create(
                    name=name,
                    description=description,
                    parent_entity=parent,
                    max_limit=max_limit,
                    **config,
                )
                messages.success(request, f"Category created successfully.")

                return redirect("entity_detail", pk=parent_entity_id)
        except Exception as e:
            print(str(e))
            messages.error(request, f"System Error: {str(e)}")

    return render(request, "app_entity/category_form.html", context={"parent": parent})
