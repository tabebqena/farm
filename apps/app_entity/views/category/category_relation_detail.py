from django.shortcuts import render

from apps.app_base.logging_utils import logger
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
    FinancialCategory,
)


def category_relation_detail_view(request, pk):
    """Display financial category assignment details."""
    logger.debug(f"Fetching category relation | relation_pk={pk}")
    relation = get_object_or_404(
        FinancialCategoriesEntitiesRelations,
        pk=pk,
        error_message="Category assignment not found or has been deleted.",
    )
    category = relation.category
    parent = relation.entity
    logger.debug(
        f"Category relation loaded | relation_id={relation.id} | "
        f"category_id={category.id} | parent_id={parent.id} | "
        f"max_limit={float(relation.max_limit) if relation.max_limit else None}"
    )

    # Calculate usage percentage for progress bar
    usage_percentage = 0

    context = {
        "category": category,
        "parent": parent,
        "relation": relation,
        "usage_percentage": usage_percentage,
    }
    return render(request, "app_entity/category/category_relation_detail.html", context)
