from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_entity.models import Category


def category_edit_view(request, pk):
    # We fetch the category; the 'entity' wrapper is accessible via category.entity
    category = get_object_or_404(Category, pk=pk)
    entity = category.entity  # The Entity wrapper for this category
    parent = category.parent_entity  # The Project/Person owner

    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description", "")
        raw_limit = request.POST.get("max_limit")
        max_limit = Decimal(raw_limit) if raw_limit else Decimal("0.00")

        # Configuration flags for the Category's Entity wrapper
        entity.active = request.POST.get("active") == "on"
        # Usually categories are internal and can't pay, but we allow editing here
        # entity.can_pay = request.POST.get("can_pay") == "on"

        try:
            with transaction.atomic():
                # Update Category details
                category.name = name
                category.description = description
                category.max_limit = max_limit
                category.save()

                # Update Entity wrapper details
                entity.save()

                messages.success(
                    request, f"Category: {category.name} updated successfully."
                )
                return redirect("entity_detail", pk=parent.id)
        except Exception as e:
            messages.error(request, f"Update Failed: {str(e)}")

    context = {
        "category": category,
        "entity": entity,
        "parent": parent,
        "is_edit": True,
    }
    return render(request, "app_entity/category_form.html", context)
