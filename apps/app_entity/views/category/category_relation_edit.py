from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
)


def category_relation_edit_view(request, pk):
    # 1. Fetch the existing category and relation
    relation = get_object_or_404(FinancialCategoriesEntitiesRelations, pk=pk)
    category = relation.category

    parent = relation.entity

    if request.method == "POST":
        action = request.POST.get("action", "save")

        try:
            with transaction.atomic():
                if action == "remove":
                    # Deactivate the relation (don't delete, preserves history)
                    relation.is_active = False
                    relation.save()
                    messages.success(
                        request, f"Category '{category.name}' removed from project."
                    )
                elif action == "activate":
                    # Deactivate the relation (don't delete, preserves history)
                    relation.is_active = True
                    relation.save()
                    messages.success(
                        request, f"Category '{category.name}' activated successfully."
                    )
                else:  # action == "save"
                    # Update the relation's max_limit only
                    raw_limit = request.POST.get("max_limit", "0.00")
                    relation.max_limit = Decimal(raw_limit)
                    relation.save()
                    messages.success(
                        request, f"Category '{category.name}' updated successfully."
                    )

                return redirect("entity_detail", pk=parent.id)

        except Exception as e:
            messages.error(request, f"Update failed: {str(e)}")

    return render(
        request,
        "app_entity/category/category_relation_edit_form.html",
        {
            "category": category,
            "parent": parent,
            "relation": relation,
        },
    )
