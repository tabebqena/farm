from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_entity.models import Entity
from apps.app_operation.models import FinancialCategory, default_categories


def category_bulk_create_view(request, parent_entity_id):
    parent = get_object_or_404(Entity, id=parent_entity_id)

    # 1. Get names of categories this project ALREADY has
    existing_names = FinancialCategory.objects.filter(parent_entity=parent).values_list(
        "name", flat=True
    )

    # 2. Filter the dictionary to show only NEW suggestions
    suggestions = {
        name: details
        for name, details in default_categories.items()
        if name not in existing_names
    }

    if request.method == "POST":
        selected_names = request.POST.getlist("selected_categories")

        categories_to_create = []
        for name in selected_names:
            if name in suggestions:
                data = suggestions[name]
                categories_to_create.append(
                    FinancialCategory(
                        parent_entity=parent,
                        name=name,
                        category_type=data["type"],
                        description=data["desc"],
                        max_limit=Decimal("0.00"),
                        is_active=True,
                    )
                )

        if categories_to_create:
            try:
                with transaction.atomic():
                    for cat in categories_to_create:
                        cat.save()
                    messages.success(
                        request,
                        f"Successfully added {len(categories_to_create)} categories.",
                    )
            except Exception as e:
                messages.error(request, f"Bulk creation failed: {str(e)}")
        else:
            messages.warning(request, "No categories were selected.")

        return redirect("entity_detail", pk=parent.id)

    return render(
        request,
        "app_operation/category/category_bulk_form.html",
        {
            "parent": parent,
            "suggestions": suggestions,
        },
    )
