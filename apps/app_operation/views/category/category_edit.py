from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_operation.models import FinancialCategory


def category_edit_view(request, pk):
    # 1. Fetch the existing category
    category = get_object_or_404(FinancialCategory, id=pk)
    parent = category.parent_entity  # The Project it belongs to

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        desc = request.POST.get("description", "")
        raw_limit = request.POST.get("max_limit", "0.00")
        is_active = request.POST.get("active") == "on"

        # 2. Check for name collisions (excluding this current record)
        if (
            FinancialCategory.objects.filter(parent_entity=parent, name__iexact=name)
            .exclude(id=category.id)
            .exists()
        ):
            messages.error(
                request,
                f"Another category named '{name}' already exists in this project.",
            )
            return redirect("category_edit", category_id=category.id)

        try:
            with transaction.atomic():
                # 3. Update the instance — category_type is immutable
                category.name = name
                category.description = desc
                category.max_limit = Decimal(raw_limit)
                category.is_active = is_active
                category.save()

                messages.success(request, f"Category '{name}' updated successfully.")
                return redirect("entity_detail", pk=parent.id)

        except Exception as e:
            messages.error(request, f"Update failed: {str(e)}")

    return render(
        request,
        "app_operation/category/category_edit_form.html",
        {
            "category": category,
            "parent": parent,
        },
    )
