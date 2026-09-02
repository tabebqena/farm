"""Category-entity relation editing view.

:class:`CategoryRelationEditView` supports remove, activate and save (max limit
update) actions on a :class:`FinancialCategoriesEntitiesRelations` record.
"""

from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views import View

from apps.app_base.logging_utils import audit_logger, build_error_details, logger
from farm.shortcuts import get_object_or_404
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
)


# Per-action audit verb (audit_logger.info prefix) and success message.
_RELATION_ACTION_VERBS = {
    "remove": "category_relation_removed",
    "activate": "category_relation_activated",
    "save": "category_relation_updated",
}

_RELATION_ACTION_MESSAGES = {
    "remove": "Category '{name}' removed from project.",
    "activate": "Category '{name}' activated successfully.",
    "save": "Category '{name}' updated successfully.",
}


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

    def _relation_audit(self, action, relation, category, parent, request, **extra):
        """Write the ``audit_logger.info`` line for a category-relation action."""
        verb = _RELATION_ACTION_VERBS.get(action, "category_relation_updated")
        extra_str = "".join(f" | {k}={v}" for k, v in extra.items())
        audit_logger.info(
            f"{verb} | FinancialCategory:{category.pk} | "
            f"user={request.user.username} | entity_id={parent.pk} | "
            f"relation_id={relation.pk}{extra_str}"
        )

    def _relation_success_message(self, action, category):
        """Return the success message for a category-relation action."""
        return _RELATION_ACTION_MESSAGES.get(
            action, "Category '{name}' updated successfully."
        ).format(name=category.name)

    def _apply_relation_action(self, request, relation, category, parent, action):
        """Apply a category-relation POST action (remove/activate/save) inside an
        atomic block — mutation, debug/audit logging and success message. Returns
        the redirect response."""
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
            elif action == "activate":
                # Activate the relation
                relation.is_active = True
                relation.save()
                logger.debug(
                    f"Category relation activated | relation_id={relation.pk} | "
                    f"category_id={category.pk}"
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

            self._relation_audit(
                action,
                relation,
                category,
                parent,
                request,
                **(
                    {"new_max_limit": relation.max_limit}
                    if action == "save"
                    else {}
                ),
            )
            messages.success(
                request, self._relation_success_message(action, category)
            )
            return redirect("entity_detail", pk=parent.pk)

    def _relation_error(self, request, e, relation, category, parent):
        """Render the edit form after a failed relation update."""
        error_details = build_error_details(
            e,
            extra={
                "action": request.POST.get("action", "save"),
                "relation_id": relation.pk,
            },
        )
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
            return self._apply_relation_action(
                request, relation, category, parent, action
            )
        except Exception as e:
            return self._relation_error(request, e, relation, category, parent)
