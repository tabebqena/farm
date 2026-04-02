import json
from decimal import Decimal

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.app_entity.models import Entity
from apps.app_operation.models import (
    FinancialCategory,
    default_categories,
)


def category_create_view(request, parent_entity_id):
    # 1. Fetch parent and validate it's a project
    parent = get_object_or_404(Entity, id=parent_entity_id)

    if not parent.project:
        messages.error(request, "Categories can only be added to Project entities.")
        return redirect("entity_detail", pk=parent_entity_id)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        category_type = request.POST.get("category_type", "EXPENSE")
        description = request.POST.get("description", "")
        raw_limit = request.POST.get("max_limit")

        try:
            max_limit = Decimal(raw_limit) if raw_limit else Decimal("0.00")

            with transaction.atomic():
                # Use update_or_create or get_or_create with BOTH name and parent_entity
                # since your model constraint is unique_together.
                category, created = FinancialCategory.objects.get_or_create(
                    name=name,
                    parent_entity=parent,
                    defaults={
                        "category_type": category_type,
                        "description": description,
                        "max_limit": max_limit,
                    },
                )

                if not created:
                    messages.warning(
                        request, f"Category '{name}' already exists for this project."
                    )
                    return redirect("entity_detail", pk=parent_entity_id)

                messages.success(request, f"Category '{name}' created successfully.")
                return redirect("entity_detail", pk=parent_entity_id)

        except (Decimal.InvalidOperation, ValueError):
            messages.error(request, "Invalid budget limit amount.")
        except IntegrityError:
            messages.error(
                request, "A database error occurred while creating the category."
            )
        except Exception as e:
            messages.error(request, f"System Error: {str(e)}")

    return render(
        request,
        "app_operation/category/category_form.html",
        context={
            "parent": parent,
            "default_categories": default_categories,
            "default_categories_json": json.dumps(default_categories),
        },
    )
