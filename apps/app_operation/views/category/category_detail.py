from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import get_object_or_404, render

from apps.app_operation.models import FinancialCategory


def category_detail_view(request, pk):
    category = get_object_or_404(FinancialCategory, id=pk)

    # Assuming you have an 'Operation' model linked to Category
    # We calculate the total spent/received in this category
    # total_spent = category.operations.filter(status="COMPLETED").aggregate(
    #     total=Sum("amount")
    # )["total"] or Decimal("0.00")

    # Calculate percentage for progress bar
    usage_percentage = 0
    # if category.max_limit > 0:
    #     usage_percentage = min(int((total_spent / category.max_limit) * 100), 100)

    context = {
        "category": category,
        "parent": category.parent_entity,
        # "total_spent": total_spent,
        "usage_percentage": usage_percentage,
        # "recent_operations": category.operations.all().order_by("-created_at")[:10],
    }
    return render(request, "app_operation/category/category_detail.html", context)
