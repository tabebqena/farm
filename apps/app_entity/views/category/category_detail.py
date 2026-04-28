from django.shortcuts import render

from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
    FinancialCategory,
)


def category_relation_detail_view(request, pk):
    relation = get_object_or_404(
        FinancialCategoriesEntitiesRelations,
        pk=pk,
        error_message="Category assignment not found or has been deleted."
    )
    category = relation.category
    parent = relation.entity

    # Assuming you have an 'Operation' model linked to Category
    # We calculate the total spent/received in this category
    # total_spent = category.operations.filter(status="COMPLETED").aggregate(
    #     total=Sum("amount")
    # )["total"] or Decimal("0.00")

    # Calculate percentage for progress bar
    usage_percentage = 0
    # if relation and relation.max_limit > 0:
    #     usage_percentage = min(int((total_spent / relation.max_limit) * 100), 100)

    context = {
        "category": category,
        "parent": parent,
        "relation": relation,
        # "total_spent": total_spent,
        "usage_percentage": usage_percentage,
        # "recent_operations": category.operations.all().order_by("-created_at")[:10],
    }
    return render(request, "app_entity/category/category_detail.html", context)
