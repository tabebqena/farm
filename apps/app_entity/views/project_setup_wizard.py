from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext

from apps.app_base.debug import DebugContext, debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import (
    Entity,
    EntityType,
    Stakeholder,
)
from apps.app_entity.models import Entity
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
    FinancialCategory,
)

from apps.app_inventory.models import ProductTemplate

STEPS = {
    1: {"name": "Project Info", "title": gettext("Initialize Project")},
    2: {"name": "Categories", "title": gettext("Financial Categories")},
    3: {"name": "Templates", "title": gettext("Product Templates")},
    4: {"name": "Workers", "title": gettext("Worker Stakeholders")},
    5: {"name": "Vendors", "title": gettext("Vendor Stakeholders")},
    6: {"name": "Shareholders", "title": gettext("Shareholder Stakeholders")},
}


@debug_view
def project_setup_wizard_view(request, entity_pk=None, step=1):
    """
    Multi-step project setup wizard.
    - Step 1: Create/edit project (Entity)
    - Steps 2-6: Configure categories, templates, and stakeholders
    Session stores wizard_entity_pk after step 1.
    """
    with DebugContext.section(
        "Initializing project setup wizard",
        {
            "entity_pk": entity_pk,
            "step": step,
            "user": request.user.username,
        },
    ):
        # Validate step number
        if step not in STEPS:
            DebugContext.warn("Invalid wizard step", {"step": step})
            DebugContext.audit(
                action="wizard_invalid_step",
                entity_type="ProjectSetupWizard",
                entity_id=None,
                details={"step": step},
                user=request.user.username,
            )
            messages.error(request, gettext("Invalid wizard step."))
            return redirect("entity_list")

        # Get or load entity
        entity = None
        if entity_pk:
            entity = get_object_or_404(
                Entity,
                pk=entity_pk,
                entity_type=EntityType.PROJECT,
                error_message="Project not found or has been deleted.",
            )
            DebugContext.success("Project loaded", {"project_id": entity.pk})
        elif step == 1:
            # Step 1 with no entity_pk means creating new
            DebugContext.success("Creating new project", {})
        else:
            # Steps 2+ require entity_pk
            error_msg = gettext("Project not found. Start from step 1.")
            DebugContext.warn("Project not found for step", {"step": step})
            DebugContext.audit(
                action="wizard_project_not_found",
                entity_type="ProjectSetupWizard",
                entity_id=None,
                details={"step": step},
                user=request.user.username,
            )
            messages.error(request, error_msg)
            return redirect("project_setup")

    # Dispatch to step handler
    if request.method == "POST":
        with DebugContext.section(
            f"Processing wizard step {step} POST",
            {
                "step": step,
                "entity_id": entity.pk if entity else None,
                "user": request.user.username,
            },
        ):
            if step == 1:
                return _handle_step_1_post(request, entity)
            elif step == 2:
                return _handle_step_2_post(request, entity)
            elif step == 3:
                return _handle_step_3_post(request, entity)
            elif step == 4:
                return _handle_step_4_post(request, entity)
            elif step == 5:
                return _handle_step_5_post(request, entity)
            elif step == 6:
                return _handle_step_6_post(request, entity)

    # GET: render the step
    with DebugContext.section(
        f"Rendering wizard step {step}",
        {
            "step": step,
            "entity_id": entity.pk if entity else None,
        },
    ):
        context = _get_step_context(request, entity, step)
        context["is_edit"] = entity is not None
        context["step"] = step
        context["total_steps"] = 6
        context["step_labels"] = STEPS
        DebugContext.success(
            f"Step {step} context built", {"entity_id": entity.pk if entity else None}
        )

    return render(request, "app_entity/project_setup_wizard.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Project Info
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_1_post(request, entity):
    """Create or edit project entity."""
    with DebugContext.section(
        "Processing project info (step 1)",
        {
            "is_edit": entity is not None,
            "user": request.user.username,
        },
    ):
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "")
        is_internal = request.POST.get("is_internal") == "on"
        is_vendor = request.POST.get("is_vendor") == "on"
        is_client = request.POST.get("is_client") == "on"
        active = request.POST.get("active") == "on"

        if not name:
            DebugContext.warn("Project name is required", {})
            DebugContext.audit(
                action="wizard_step1_validation_failed",
                entity_type="ProjectSetupWizard",
                entity_id=None,
                details={"reason": "missing_name"},
                user=request.user.username,
            )
            messages.error(request, gettext("Project name is required."))
            return redirect("project_setup")

        try:
            with transaction.atomic():
                with DebugContext.section(
                    "Saving project",
                    {
                        "action": "edit" if entity else "create",
                        "name": name,
                    },
                ):
                    if entity:
                        # Edit mode
                        entity.name = name
                        entity.description = description
                        entity.is_internal = is_internal
                        entity.is_vendor = is_vendor
                        entity.is_client = is_client
                        entity.active = active
                        entity.save()
                        DebugContext.success(
                            "Project updated", {"project_id": entity.pk}
                        )
                        DebugContext.audit(
                            action="wizard_project_updated",
                            entity_type="ProjectSetupWizard",
                            entity_id=entity.pk,
                            details={"name": name},
                            user=request.user.username,
                        )
                        messages.success(
                            request, gettext("Project updated successfully.")
                        )
                        return redirect(
                            "project_setup_step", entity_pk=entity.pk, step=2
                        )
                    else:
                        # Create mode
                        entity = Entity.create(
                            entity_type=EntityType.PROJECT,
                            name=name,
                            description=description,
                            is_internal=is_internal,
                            is_vendor=is_vendor,
                            is_client=is_client,
                            active=active,
                        )
                        request.session["wizard_entity_pk"] = entity.pk
                        DebugContext.success(
                            "Project created", {"project_id": entity.pk}
                        )
                        DebugContext.audit(
                            action="wizard_project_created",
                            entity_type="ProjectSetupWizard",
                            entity_id=entity.pk,
                            details={"name": name},
                            user=request.user.username,
                        )
                        messages.success(
                            request,
                            gettext(
                                "Project '%(name)s' created. Proceeding with setup..."
                            )
                            % {"name": entity.name},
                        )
                        return redirect(
                            "project_setup_step", entity_pk=entity.pk, step=2
                        )
        except Exception as e:
            error_details = {
                "exception_type": type(e).__name__,
                "error_message": str(e),
            }
            DebugContext.error("Project save failed", e, error_details)
            DebugContext.audit(
                action="wizard_step1_failed",
                entity_type="ProjectSetupWizard",
                entity_id=entity.pk if entity else None,
                details=error_details,
                user=request.user.username,
            )
            messages.error(
                request,
                gettext("Failed to save project: %(error)s") % {"error": str(e)},
            )
            return redirect("project_setup")


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Financial Categories
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_2_post(request, entity):
    """Manage financial category links: create/activate/deactivate relations."""
    with DebugContext.section(
        "Processing financial categories (step 2)",
        {
            "entity_id": entity.pk if entity else None,
            "user": request.user.username,
        },
    ):
        if not entity:
            DebugContext.warn("Project not found", {})
            DebugContext.audit(
                action="wizard_step2_project_not_found",
                entity_type="ProjectSetupWizard",
                entity_id=None,
                details={},
                user=request.user.username,
            )
            messages.error(request, gettext("Project not found."))
            return redirect("project_setup")

        selected_pks = set(request.POST.getlist("selected_categories"))
        # Convert to integers for comparison
        try:
            selected_pks = {int(pk) for pk in selected_pks if pk}
        except ValueError:
            DebugContext.warn(
                "Invalid category selection", {"selected_count": len(selected_pks)}
            )
            DebugContext.audit(
                action="wizard_step2_validation_failed",
                entity_type="ProjectSetupWizard",
                entity_id=entity.pk,
                details={"reason": "invalid_category_selection"},
                user=request.user.username,
            )
            messages.error(request, gettext("Invalid category selection."))
            return redirect("project_setup_step", entity_pk=entity.pk, step=2)

        try:
            with transaction.atomic():
                with DebugContext.section(
                    "Updating category relations",
                    {
                        "entity_id": entity.pk,
                        "selected_count": len(selected_pks),
                    },
                ):
                    # Get all existing relations for this entity
                    existing_relations = {
                        r.category.id: r
                        for r in FinancialCategoriesEntitiesRelations.objects.filter(
                            entity=entity
                        ).select_related("category")
                    }

                    # Handle existing relations: activate if selected, deactivate if not
                    for category_id, relation in existing_relations.items():
                        if category_id in selected_pks:
                            if not relation.is_active:
                                relation.is_active = True
                                relation.save()
                        else:
                            if relation.is_active:
                                relation.is_active = False
                                relation.save()

                    # Create new relations for newly selected categories
                    new_count = 0
                    for category_id in selected_pks - existing_relations.keys():
                        try:
                            category = FinancialCategory.objects.get(pk=category_id)
                            FinancialCategoriesEntitiesRelations.objects.get_or_create(
                                entity=entity,
                                category=category,
                                defaults={
                                    "is_active": True,
                                    "max_limit": Decimal("0.00"),
                                },
                            )
                            new_count += 1
                        except FinancialCategory.DoesNotExist:
                            pass

                    DebugContext.success(
                        "Categories updated",
                        {
                            "entity_id": entity.pk,
                            "new_count": new_count,
                            "total_selected": len(selected_pks),
                        },
                    )
                    DebugContext.audit(
                        action="wizard_categories_updated",
                        entity_type="ProjectSetupWizard",
                        entity_id=entity.pk,
                        details={
                            "selected_count": len(selected_pks),
                            "new_count": new_count,
                        },
                        user=request.user.username,
                    )

            messages.success(request, gettext("Categories updated successfully."))
        except Exception as e:
            error_details = {
                "exception_type": type(e).__name__,
                "error_message": str(e),
            }
            DebugContext.error("Category update failed", e, error_details)
            DebugContext.audit(
                action="wizard_step2_failed",
                entity_type="ProjectSetupWizard",
                entity_id=entity.pk,
                details=error_details,
                user=request.user.username,
            )
            messages.error(
                request,
                gettext("Failed to update categories: %(error)s") % {"error": str(e)},
            )

    return redirect("project_setup_step", entity_pk=entity.pk, step=3)


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Product Templates
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_3_post(request, entity):
    """Assign product templates to entity."""
    with DebugContext.section(
        "Processing product templates (step 3)",
        {
            "entity_id": entity.pk if entity else None,
            "user": request.user.username,
        },
    ):
        if not entity:
            DebugContext.warn("Project not found", {})
            DebugContext.audit(
                action="wizard_step3_project_not_found",
                entity_type="ProjectSetupWizard",
                entity_id=None,
                details={},
                user=request.user.username,
            )
            messages.error(request, gettext("Project not found."))
            return redirect("project_setup")

        if not request.user.is_staff:
            DebugContext.warn(
                "User lacks staff permission", {"user": request.user.username}
            )
            DebugContext.audit(
                action="wizard_step3_permission_denied",
                entity_type="ProjectSetupWizard",
                entity_id=entity.pk,
                details={"reason": "not_staff"},
                user=request.user.username,
            )
            messages.error(
                request,
                gettext("You do not have permission to manage product templates."),
            )
            return redirect("project_setup_step", entity_pk=entity.pk, step=3)

        template_ids = request.POST.getlist("product_templates")

        try:
            with transaction.atomic():
                with DebugContext.section(
                    "Assigning product templates",
                    {
                        "entity_id": entity.pk,
                        "template_count": len(template_ids),
                    },
                ):
                    entity.product_templates.set(template_ids)
                    DebugContext.success(
                        "Templates assigned",
                        {
                            "entity_id": entity.pk,
                            "template_count": len(template_ids),
                        },
                    )
                    DebugContext.audit(
                        action="wizard_templates_assigned",
                        entity_type="ProjectSetupWizard",
                        entity_id=entity.pk,
                        details={"template_count": len(template_ids)},
                        user=request.user.username,
                    )

                if template_ids:
                    messages.success(
                        request,
                        gettext("Product templates assigned successfully."),
                    )
                else:
                    messages.info(request, gettext("No product templates selected."))
        except Exception as e:
            error_details = {
                "exception_type": type(e).__name__,
                "error_message": str(e),
            }
            DebugContext.error("Template assignment failed", e, error_details)
            DebugContext.audit(
                action="wizard_step3_failed",
                entity_type="ProjectSetupWizard",
                entity_id=entity.pk,
                details=error_details,
                user=request.user.username,
            )
            messages.error(
                request,
                gettext("Failed to assign templates: %(error)s") % {"error": str(e)},
            )

    return redirect("project_setup_step", entity_pk=entity.pk, step=4)


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Worker Stakeholders
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_4_post(request, entity):
    """Add worker stakeholders."""
    return _handle_stakeholder_post(request, entity, "worker", 5)


# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Vendor Stakeholders
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_5_post(request, entity):
    """Add vendor stakeholders."""
    return _handle_stakeholder_post(request, entity, "vendor", 6)


# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Shareholder Stakeholders
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_6_post(request, entity):
    """Add shareholder stakeholders. Final step, redirect to entity_detail."""
    with DebugContext.section(
        "Processing shareholders (step 6 - Final)",
        {
            "entity_id": entity.pk if entity else None,
            "user": request.user.username,
        },
    ):
        if not entity:
            DebugContext.warn("Project not found", {})
            DebugContext.audit(
                action="wizard_step6_project_not_found",
                entity_type="ProjectSetupWizard",
                entity_id=None,
                details={},
                user=request.user.username,
            )
            messages.error(request, gettext("Project not found."))
            return redirect("project_setup")

        selected_ids = request.POST.getlist("selected_entities")

        try:
            with transaction.atomic():
                with DebugContext.section(
                    "Adding shareholder stakeholders",
                    {
                        "entity_id": entity.pk,
                        "shareholder_count": len(selected_ids),
                    },
                ):
                    created_count = 0
                    for target_id in selected_ids:
                        try:
                            target = Entity.objects.get(
                                pk=target_id, is_shareholder=True, active=True
                            )
                            _, created = Stakeholder.objects.get_or_create(
                                parent=entity,
                                target=target,
                                role="shareholder",
                            )
                            if created:
                                created_count += 1
                        except Entity.DoesNotExist:
                            pass

                    DebugContext.success(
                        "Shareholders added",
                        {
                            "entity_id": entity.pk,
                            "created_count": created_count,
                            "total_count": len(selected_ids),
                        },
                    )
                    DebugContext.audit(
                        action="wizard_shareholders_added",
                        entity_type="ProjectSetupWizard",
                        entity_id=entity.pk,
                        details={"count": created_count},
                        user=request.user.username,
                    )

                if selected_ids:
                    messages.success(
                        request, gettext("Shareholders added successfully.")
                    )
                else:
                    messages.info(request, gettext("No shareholders selected."))
        except Exception as e:
            error_details = {
                "exception_type": type(e).__name__,
                "error_message": str(e),
            }
            DebugContext.error("Shareholder addition failed", e, error_details)
            DebugContext.audit(
                action="wizard_step6_failed",
                entity_type="ProjectSetupWizard",
                entity_id=entity.pk,
                details=error_details,
                user=request.user.username,
            )
            messages.error(
                request,
                gettext("Failed to add shareholders: %(error)s") % {"error": str(e)},
            )

        DebugContext.success(
            "Project setup completed",
            {
                "entity_id": entity.pk,
                "project_name": entity.name,
            },
        )
        DebugContext.audit(
            action="wizard_completed",
            entity_type="ProjectSetupWizard",
            entity_id=entity.pk,
            details={"project_name": entity.name},
            user=request.user.username,
        )
        messages.success(
            request, gettext("Project setup completed! Configure operations as needed.")
        )
        return redirect("entity_detail", pk=entity.pk)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Generic Stakeholder POST Handler
# ─────────────────────────────────────────────────────────────────────────────


def _handle_stakeholder_post(request, entity, role_type, next_step):
    """Generic handler for workers, vendors, and other stakeholders."""
    with DebugContext.section(
        f"Processing {role_type} stakeholders",
        {
            "entity_id": entity.pk if entity else None,
            "role_type": role_type,
            "user": request.user.username,
        },
    ):
        if not entity:
            DebugContext.warn("Project not found", {})
            DebugContext.audit(
                action=f"wizard_step{next_step-1}_project_not_found",
                entity_type="ProjectSetupWizard",
                entity_id=None,
                details={},
                user=request.user.username,
            )
            messages.error(request, gettext("Project not found."))
            return redirect("project_setup")

        selected_ids = request.POST.getlist("selected_entities")

        # Determine eligibility filter based on role
        if role_type == "worker":
            filter_kwargs = {"is_worker": True, "active": True}
        elif role_type == "vendor":
            filter_kwargs = {"is_vendor": True, "active": True}
        elif role_type == "shareholder":
            filter_kwargs = {"is_shareholder": True, "active": True}
        else:
            DebugContext.warn("Invalid role type", {"role_type": role_type})
            DebugContext.audit(
                action="wizard_invalid_role_type",
                entity_type="ProjectSetupWizard",
                entity_id=entity.pk if entity else None,
                details={"role_type": role_type},
                user=request.user.username,
            )
            messages.error(request, gettext("Invalid role type."))
            return redirect(
                "project_setup_step", entity_pk=entity.pk, step=next_step - 1
            )

        try:
            with transaction.atomic():
                with DebugContext.section(
                    f"Adding {role_type} stakeholders",
                    {
                        "entity_id": entity.pk,
                        "stakeholder_count": len(selected_ids),
                    },
                ):
                    created_count = 0
                    for target_id in selected_ids:
                        try:
                            target = Entity.objects.get(pk=target_id, **filter_kwargs)
                            _, created = Stakeholder.objects.get_or_create(
                                parent=entity,
                                target=target,
                                role=role_type,
                            )
                            if created:
                                created_count += 1
                        except Entity.DoesNotExist:
                            pass

                    DebugContext.success(
                        f"{role_type} stakeholders added",
                        {
                            "entity_id": entity.pk,
                            "created_count": created_count,
                            "total_count": len(selected_ids),
                        },
                    )
                    DebugContext.audit(
                        action=f"wizard_{role_type}_stakeholders_added",
                        entity_type="ProjectSetupWizard",
                        entity_id=entity.pk,
                        details={"role_type": role_type, "count": created_count},
                        user=request.user.username,
                    )

                if selected_ids:
                    messages.success(
                        request,
                        gettext("%(role)s added successfully.")
                        % {"role": role_type.capitalize()},
                    )
                else:
                    messages.info(
                        request, gettext("No %(role)s selected.") % {"role": role_type}
                    )
        except Exception as e:
            error_details = {
                "exception_type": type(e).__name__,
                "error_message": str(e),
                "role_type": role_type,
            }
            DebugContext.error(
                f"Stakeholder addition failed ({role_type})", e, error_details
            )
            DebugContext.audit(
                action=f"wizard_step{next_step-1}_failed",
                entity_type="ProjectSetupWizard",
                entity_id=entity.pk,
                details=error_details,
                user=request.user.username,
            )
            messages.error(
                request,
                gettext("Failed to add %(role)s: %(error)s")
                % {"role": role_type, "error": str(e)},
            )

    return redirect("project_setup_step", entity_pk=entity.pk, step=next_step)


# ─────────────────────────────────────────────────────────────────────────────
# GET Context Builders
# ─────────────────────────────────────────────────────────────────────────────


def _get_step_context(request, entity, step):
    """Build context dict for the current step."""
    context = {"entity": entity}

    if step == 1:
        # No additional context needed; form will use entity fields
        pass

    elif step == 2:
        # Get already-linked category relations grouped by aspect
        if entity:
            # All relations for this entity (active or inactive)
            linked_relations = FinancialCategoriesEntitiesRelations.objects.filter(
                entity=entity
            ).select_related("category")

            # Group linked categories by aspect
            linked_by_aspect = {}
            linked_ids = set()
            for relation in linked_relations:
                aspect = relation.category.aspect
                if aspect not in linked_by_aspect:
                    linked_by_aspect[aspect] = []
                linked_by_aspect[aspect].append(relation)
                linked_ids.add(relation.category.id)

            # All categories not yet linked, grouped by aspect
            available_categories = FinancialCategory.objects.exclude(
                id__in=linked_ids
            ).order_by("aspect", "name")

            available_by_aspect = {}
            for category in available_categories:
                aspect = category.aspect
                if aspect not in available_by_aspect:
                    available_by_aspect[aspect] = []
                available_by_aspect[aspect].append(category)
        else:
            linked_by_aspect = {}
            linked_ids = set()
            available_by_aspect = {}
            available_categories = FinancialCategory.objects.order_by("aspect", "name")
            for category in available_categories:
                aspect = category.aspect
                if aspect not in available_by_aspect:
                    available_by_aspect[aspect] = []
                available_by_aspect[aspect].append(category)

        context["linked_by_aspect"] = linked_by_aspect
        context["available_by_aspect"] = available_by_aspect

    elif step == 3:
        # Product templates: show all, highlight assigned
        if entity:
            all_templates = ProductTemplate.objects.all().order_by(
                "nature", "sub_category", "name"
            )
            enabled_ids = set(entity.product_templates.values_list("id", flat=True))
            context["templates"] = all_templates
            context["enabled_ids"] = enabled_ids
        else:
            context["templates"] = ProductTemplate.objects.none()
            context["enabled_ids"] = set()

    elif step == 4:
        # Workers: eligible persons flagged as is_worker
        if entity:
            eligible = (
                Entity.objects.filter(is_worker=True, active=True)
                .exclude(id=entity.id)
                .order_by("name")
            )
            existing = set(
                Stakeholder.objects.filter(parent=entity, role="worker").values_list(
                    "target_id", flat=True
                )
            )
        else:
            eligible = Entity.objects.none()
            existing = set()

        context["eligible_entities"] = eligible
        context["existing_stakeholder_ids"] = existing

    elif step == 5:
        # Vendors: entities flagged as is_vendor
        if entity:
            eligible = (
                Entity.objects.filter(is_vendor=True, active=True)
                .exclude(id=entity.id)
                .order_by("name")
            )
            existing = set(
                Stakeholder.objects.filter(parent=entity, role="vendor").values_list(
                    "target_id", flat=True
                )
            )
        else:
            eligible = Entity.objects.none()
            existing = set()

        context["eligible_entities"] = eligible
        context["existing_stakeholder_ids"] = existing

    elif step == 6:
        # Shareholders: persons flagged as is_shareholder
        if entity:
            eligible = (
                Entity.objects.filter(is_shareholder=True, active=True)
                .exclude(id=entity.id)
                .order_by("name")
            )
            existing = set(
                Stakeholder.objects.filter(
                    parent=entity, role="shareholder"
                ).values_list("target_id", flat=True)
            )
        else:
            eligible = Entity.objects.none()
            existing = set()

        context["eligible_entities"] = eligible
        context["existing_stakeholder_ids"] = existing
    context["step_nums"] = (
        1,
        2,
        3,
        4,
        5,
        6,
    )
    return context
