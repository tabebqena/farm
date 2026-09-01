from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views import View

from apps.app_base.logging_utils import audit_logger, logger
from farm.shortcuts import get_object_or_404
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
)


class CategoryRelationEditView(View):
    """Edit a category-entity relationship (max limit and activation)."""

    def _setup(self, pk):
        """Load the relation, category and parent. Returns ``(relation, category, parent, response)``."""
        # 1. Fetch the existing category and relation
        logger.debug(
            f"Fetching category relation | relation_pk={pk} | user={self.request.user.username}"
        )
        relation = get_object_or_404(
            FinancialCategoriesEntitiesRelations,
            pk=pk,
            error_message="Category assignment not found or has been deleted."
        )
        category = relation.category
        parent = relation.entity
        logger.debug(
            f"Category relation loaded | relation_id={relation.pk} | "
            f"category_id={category.pk} | entity_id={parent.pk} | "
            f"is_active={relation.is_active} | max_limit={relation.max_limit}"
        )
        return relation, category, parent, None

    def get(self, request, *args, **kwargs):
        relation, category, parent, response = self._setup(kwargs["pk"])
        if response is not None:
            return response

        return render(
            request,
            "app_entity/category/category_relation_edit_form.html",
            {
                "category": category,
                "parent": parent,
                "relation": relation,
            },
        )

    def post(self, request, *args, **kwargs):
        relation, category, parent, response = self._setup(kwargs["pk"])
        if response is not None:
            return response

        logger.debug(
            f"Processing category relation update | relation_pk={relation.pk} | "
            f"user={request.user.username}"
        )
        action = request.POST.get("action", "save")

        try:
            with transaction.atomic():
                logger.debug(
                    f"Executing action: {action} | action={action} | "
                    f"relation_id={relation.pk} | category_id={category.pk}"
                )
                if action == "remove":
                    # Deactivate the relation (don't delete, preserves history)
                    relation.is_active = False
                    relation.save()
                    logger.debug(
                        f"Category relation deactivated | relation_id={relation.pk} | "
                        f"category_id={category.pk}"
                    )
                    audit_logger.info(
                        f"category_relation_removed | FinancialCategory:{category.pk} | "
                        f"user={request.user.username} | entity_id={parent.pk} | "
                        f"relation_id={relation.pk}"
                    )
                    messages.success(
                        request, f"Category '{category.name}' removed from project."
                    )
                elif action == "activate":
                    # Activate the relation
                    relation.is_active = True
                    relation.save()
                    logger.debug(
                        f"Category relation activated | relation_id={relation.pk} | "
                        f"category_id={category.pk}"
                    )
                    audit_logger.info(
                        f"category_relation_activated | FinancialCategory:{category.pk} | "
                        f"user={request.user.username} | entity_id={parent.pk} | "
                        f"relation_id={relation.pk}"
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
                    logger.debug(
                        f"Category relation updated | relation_id={relation.pk} | "
                        f"category_id={category.pk} | old_limit={old_limit} | "
                        f"new_limit={relation.max_limit}"
                    )
                    audit_logger.info(
                        f"category_relation_updated | FinancialCategory:{category.pk} | "
                        f"user={request.user.username} | entity_id={parent.pk} | "
                        f"relation_id={relation.pk} | new_max_limit={relation.max_limit}"
                    )
                    messages.success(
                        request, f"Category '{category.name}' updated successfully."
                    )

                return redirect("entity_detail", pk=parent.pk)

        except Exception as e:
            error_details = {
                "exception_type": type(e).__name__,
                "error_message": str(e),
                "action": action,
                "relation_id": relation.pk,
            }
            logger.error(
                f"Category relation update failed | "
                f"exception_type={error_details['exception_type']} | "
                f"error_message={error_details['error_message']} | "
                f"relation_id={relation.pk}"
            )
            audit_logger.error(
                f"category_relation_update_failed | FinancialCategory:{category.pk} | "
                f"user={request.user.username} | error={error_details}"
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
