from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_entity.models import Entity
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
    FinancialCategory,
)


def category_bulk_assign_view(request, parent_entity_id):
    parent_entity = get_object_or_404(Entity, id=parent_entity_id)
    categories = FinancialCategory.objects.all()

    if request.method == "POST":
        selected_pks = request.POST.getlist("selected_categories")
        created_count = 0
        removed_count = 0
        try:
            with transaction.atomic():
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

                if created_count > 0 or removed_count > 0:
                    messages.success(
                        request,
                        f"Successfully added {created_count} categories, remove {removed_count} categories.",
                    )
                else:
                    messages.warning(request, "No new categories were added.")
        except Exception as e:
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
