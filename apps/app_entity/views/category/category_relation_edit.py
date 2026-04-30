from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
)


@debug_view
def category_relation_edit_view(request, pk):
    """Edit a category-entity relationship (max limit and activation)."""
    # 1. Fetch the existing category and relation
    with DebugContext.section("Fetching category relation", {"relation_pk": pk, "user": request.user.username}):
        relation = get_object_or_404(
            FinancialCategoriesEntitiesRelations,
            pk=pk,
            error_message="Category assignment not found or has been deleted."
        )
        category = relation.category
        parent = relation.entity
        DebugContext.success("Category relation loaded", {
            "relation_id": relation.pk,
            "category_id": category.pk,
            "entity_id": parent.pk,
            "is_active": relation.is_active,
            "max_limit": str(relation.max_limit),
        })

    if request.method == "POST":
        with DebugContext.section("Processing category relation update", {
            "relation_pk": pk,
            "user": request.user.username,
        }):
            action = request.POST.get("action", "save")

            try:
                with transaction.atomic():
                    with DebugContext.section(f"Executing action: {action}", {
                        "action": action,
                        "relation_id": relation.pk,
                        "category_id": category.pk,
                    }):
                        if action == "remove":
                            # Deactivate the relation (don't delete, preserves history)
                            relation.is_active = False
                            relation.save()
                            DebugContext.success("Category relation deactivated", {
                                "relation_id": relation.pk,
                                "category_id": category.pk,
                            })
                            DebugContext.audit(
                                action="category_relation_removed",
                                entity_type="FinancialCategory",
                                entity_id=category.pk,
                                details={
                                    "entity_id": parent.pk,
                                    "relation_id": relation.pk,
                                },
                                user=request.user.username
                            )
                            messages.success(
                                request, f"Category '{category.name}' removed from project."
                            )
                        elif action == "activate":
                            # Activate the relation
                            relation.is_active = True
                            relation.save()
                            DebugContext.success("Category relation activated", {
                                "relation_id": relation.pk,
                                "category_id": category.pk,
                            })
                            DebugContext.audit(
                                action="category_relation_activated",
                                entity_type="FinancialCategory",
                                entity_id=category.pk,
                                details={
                                    "entity_id": parent.pk,
                                    "relation_id": relation.pk,
                                },
                                user=request.user.username
                            )
                            messages.success(
                                request, f"Category '{category.name}' activated successfully."
                            )
                        else:  # action == "save"
                            # Update the relation's max_limit only
                            raw_limit = request.POST.get("max_limit", "0.00")
                            old_limit = relation.max_limit
                            relation.max_limit = Decimal(raw_limit)
                            relation.save()
                            DebugContext.success("Category relation updated", {
                                "relation_id": relation.pk,
                                "category_id": category.pk,
                                "old_limit": str(old_limit),
                                "new_limit": str(relation.max_limit),
                            })
                            DebugContext.audit(
                                action="category_relation_updated",
                                entity_type="FinancialCategory",
                                entity_id=category.pk,
                                details={
                                    "entity_id": parent.pk,
                                    "relation_id": relation.pk,
                                    "new_max_limit": str(relation.max_limit),
                                },
                                user=request.user.username
                            )
                            messages.success(
                                request, f"Category '{category.name}' updated successfully."
                            )

                    return redirect("entity_detail", pk=parent.id)

            except Exception as e:
                error_details = {
                    "exception_type": type(e).__name__,
                    "error_message": str(e),
                    "action": action,
                    "relation_id": relation.pk,
                }
                DebugContext.error("Category relation update failed", e, error_details)
                DebugContext.audit(
                    action="category_relation_update_failed",
                    entity_type="FinancialCategory",
                    entity_id=category.pk,
                    details=error_details,
                    user=request.user.username
                )
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
