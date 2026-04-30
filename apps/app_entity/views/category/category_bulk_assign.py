from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
    FinancialCategory,
)


@debug_view
def category_bulk_assign_view(request, parent_entity_id):
    """Bulk assign or remove financial categories for an entity."""
    with DebugContext.section("Fetching entity and categories", {
        "entity_id": parent_entity_id,
        "user": request.user.username,
    }):
        parent_entity = get_object_or_404(
            Entity,
            id=parent_entity_id,
            error_message="Entity not found or has been deleted."
        )
        categories = FinancialCategory.objects.all()
        DebugContext.success("Entity and categories loaded", {
            "entity_id": parent_entity.pk,
            "category_count": categories.count(),
        })

    if request.method == "POST":
        with DebugContext.section("Processing bulk category assignment", {
            "entity_id": parent_entity_id,
            "user": request.user.username,
        }):
            selected_pks = request.POST.getlist("selected_categories")
            created_count = 0
            removed_count = 0
            try:
                with transaction.atomic():
                    with DebugContext.section("Updating category relations", {
                        "selected_count": len(selected_pks),
                        "total_categories": categories.count(),
                    }):
                        for cat in categories:
                            # if category in selected_pks => create relation or activate it
                            # if not set is_active = False
                            relation_created = False
                            if str(cat.pk) in selected_pks:
                                relation, relation_created = (
                                    FinancialCategoriesEntitiesRelations.objects.get_or_create(
                                        entity=parent_entity, category=cat
                                    )
                                )
                                relation.is_active = True
                                relation.save()
                            else:
                                relation = FinancialCategoriesEntitiesRelations.objects.filter(
                                    entity=parent_entity,
                                    category=cat,
                                ).first()
                                if relation:
                                    relation.is_active = False
                                    relation.save()
                                    removed_count += 1

                            if relation_created:
                                created_count += 1

                        DebugContext.success("Category relations updated", {
                            "created_count": created_count,
                            "removed_count": removed_count,
                        })

                    if created_count > 0 or removed_count > 0:
                        DebugContext.audit(
                            action="categories_bulk_assigned",
                            entity_type="FinancialCategory",
                            entity_id=parent_entity.pk,
                            details={
                                "created_count": created_count,
                                "removed_count": removed_count,
                            },
                            user=request.user.username
                        )
                        messages.success(
                            request,
                            f"Successfully added {created_count} categories, remove {removed_count} categories.",
                        )
                    else:
                        messages.warning(request, "No new categories were added.")
            except Exception as e:
                error_details = {
                    "exception_type": type(e).__name__,
                    "error_message": str(e),
                    "entity_id": parent_entity.pk,
                }
                DebugContext.error("Bulk category assignment failed", e, error_details)
                DebugContext.audit(
                    action="bulk_category_assignment_failed",
                    entity_type="FinancialCategory",
                    entity_id=parent_entity.pk,
                    details=error_details,
                    user=request.user.username
                )
                messages.error(request, f"Bulk creation failed: {str(e)}")

            return redirect("entity_detail", pk=parent_entity.id)

    existing_names = FinancialCategoriesEntitiesRelations.objects.filter(
        entity=parent_entity, is_active=True
    ).values_list(
        # "category__name",
        "category__pk",
        flat=True,
    )
    existing_pks_set = set(existing_names)

    return render(
        request,
        "app_entity/category/category_bulk_form.html",
        {
            "parent": parent_entity,
            "categories": categories,
            "existing_category_names": existing_pks_set,
        },
    )
