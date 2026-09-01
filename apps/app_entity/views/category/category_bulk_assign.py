from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.views import View

from apps.app_base.logging_utils import audit_logger, logger
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
    FinancialCategory,
)


class CategoryBulkAssignView(View):
    """Bulk assign or remove financial categories for an entity."""

    def _setup(self, parent_entity_id):
        """Load the entity and all categories. Returns ``(parent_entity, categories, response)``."""
        logger.debug(
            f"Fetching entity and categories | entity_id={parent_entity_id} | "
            f"user={self.request.user.username}"
        )
        parent_entity = get_object_or_404(
            Entity,
            id=parent_entity_id,
            error_message="Entity not found or has been deleted."
        )
        categories = FinancialCategory.objects.all()
        logger.debug(
            f"Entity and categories loaded | entity_id={parent_entity.pk} | "
            f"category_count={categories.count()}"
        )
        return parent_entity, categories, None

    def _existing_relation_pks(self, entity):
        """Active category pks already linked to the entity."""
        existing_names = FinancialCategoriesEntitiesRelations.objects.filter(
            entity=entity, is_active=True
        ).values_list("category__pk", flat=True)
        return set(existing_names)

    def get(self, request, *args, **kwargs):
        parent_entity, categories, response = self._setup(kwargs["parent_entity_id"])
        if response is not None:
            return response

        return render(
            request,
            "app_entity/category/category_bulk_form.html",
            {
                "parent": parent_entity,
                "categories": categories,
                "existing_category_names": self._existing_relation_pks(parent_entity),
            },
        )

    def _apply_bulk_assign(self, request, parent_entity, categories):
        """Apply the bulk category assignment inside an atomic block — the
        per-row get-or-create/activate/deactivate loop. Returns
        ``(created_count, removed_count)``."""
        selected_pks = request.POST.getlist("selected_categories")
        created_count = 0
        removed_count = 0
        with transaction.atomic():
            logger.debug(
                f"Updating category relations | selected_count={len(selected_pks)} | "
                f"total_categories={categories.count()}"
            )
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

            logger.debug(
                f"Category relations updated | created_count={created_count} | "
                f"removed_count={removed_count}"
            )
        return created_count, removed_count

    def _bulk_assign_post(self, request, parent_entity, categories):
        """Handle the bulk-assign POST: apply relations, then audit + message."""
        created_count, removed_count = self._apply_bulk_assign(
            request, parent_entity, categories
        )
        if created_count > 0 or removed_count > 0:
            audit_logger.info(
                f"categories_bulk_assigned | FinancialCategory:{parent_entity.pk} | "
                f"user={request.user.username} | created_count={created_count} | "
                f"removed_count={removed_count}"
            )
            messages.success(
                request,
                f"Successfully added {created_count} categories, remove {removed_count} categories.",
            )
        else:
            messages.warning(request, "No new categories were added.")

    def post(self, request, *args, **kwargs):
        parent_entity, categories, response = self._setup(kwargs["parent_entity_id"])
        if response is not None:
            return response

        logger.debug(
            f"Processing bulk category assignment | entity_id={parent_entity.pk} | "
            f"user={request.user.username}"
        )
        try:
            self._bulk_assign_post(request, parent_entity, categories)
        except Exception as e:
            error_details = {
                "exception_type": type(e).__name__,
                "error_message": str(e),
                "entity_id": parent_entity.pk,
            }
            logger.error(
                f"Bulk category assignment failed | "
                f"exception_type={error_details['exception_type']} | "
                f"error_message={error_details['error_message']} | "
                f"entity_id={parent_entity.pk}"
            )
            audit_logger.error(
                f"bulk_category_assignment_failed | FinancialCategory:{parent_entity.pk} | "
                f"user={request.user.username} | error={error_details}"
            )
            messages.error(request, f"Bulk creation failed: {str(e)}")

        return redirect("entity_detail", pk=parent_entity.pk)
