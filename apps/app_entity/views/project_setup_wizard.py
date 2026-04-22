from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

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
    1: {"name": "Project Info", "title": _("Initialize Project")},
    2: {"name": "Categories", "title": _("Financial Categories")},
    3: {"name": "Templates", "title": _("Product Templates")},
    4: {"name": "Workers", "title": _("Worker Stakeholders")},
    5: {"name": "Vendors", "title": _("Vendor Stakeholders")},
    6: {"name": "Shareholders", "title": _("Shareholder Stakeholders")},
}


def project_setup_wizard_view(request, entity_pk=None, step=1):
    """
    Multi-step project setup wizard.
    - Step 1: Create/edit project (Entity)
    - Steps 2-6: Configure categories, templates, and stakeholders
    Session stores wizard_entity_pk after step 1.
    """

    # Validate step number
    if step not in STEPS:
        messages.error(request, _("Invalid wizard step."))
        return redirect("entity_list")

    # Get or load entity
    entity = None
    if entity_pk:
        entity = get_object_or_404(Entity, pk=entity_pk, entity_type=EntityType.PROJECT)
    elif step == 1:
        # Step 1 with no entity_pk means creating new
        pass
    else:
        # Steps 2+ require entity_pk
        messages.error(request, _("Project not found. Start from step 1."))
        return redirect("project_setup")

    # Dispatch to step handler
    if request.method == "POST":
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
    context = _get_step_context(request, entity, step)
    context["is_edit"] = entity is not None
    context["step"] = step
    context["total_steps"] = 6
    context["step_labels"] = STEPS

    return render(request, "app_entity/project_setup_wizard.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Project Info
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_1_post(request, entity):
    """Create or edit project entity."""
    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "")
    is_internal = request.POST.get("is_internal") == "on"
    is_vendor = request.POST.get("is_vendor") == "on"
    is_client = request.POST.get("is_client") == "on"
    active = request.POST.get("active") == "on"

    if not name:
        messages.error(request, _("Project name is required."))
        return redirect("project_setup")

    try:
        with transaction.atomic():
            if entity:
                # Edit mode
                entity.name = name
                entity.description = description
                entity.is_internal = is_internal
                entity.is_vendor = is_vendor
                entity.is_client = is_client
                entity.active = active
                entity.save()
                messages.success(request, _("Project updated successfully."))
                return redirect("project_setup_step", entity_pk=entity.pk, step=2)
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
                messages.success(
                    request,
                    _("Project '%(name)s' created. Proceeding with setup...")
                    % {"name": entity.name},
                )
                return redirect("project_setup_step", entity_pk=entity.pk, step=2)
    except Exception as e:
        messages.error(
            request, _("Failed to save project: %(error)s") % {"error": str(e)}
        )
        return redirect("project_setup")


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Financial Categories
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_2_post(request, entity):
    """Manage financial category links: create/activate/deactivate relations."""
    if not entity:
        messages.error(request, _("Project not found."))
        return redirect("project_setup")

    selected_pks = set(request.POST.getlist("selected_categories"))
    # Convert to integers for comparison
    try:
        selected_pks = {int(pk) for pk in selected_pks if pk}
    except ValueError:
        messages.error(request, _("Invalid category selection."))
        return redirect("project_setup_step", entity_pk=entity.pk, step=2)

    try:
        with transaction.atomic():
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
            for category_id in selected_pks - existing_relations.keys():
                try:
                    category = FinancialCategory.objects.get(pk=category_id)
                    FinancialCategoriesEntitiesRelations.objects.get_or_create(
                        entity=entity,
                        category=category,
                        defaults={"is_active": True, "max_limit": Decimal("0.00")},
                    )
                except FinancialCategory.DoesNotExist:
                    pass

            messages.success(request, _("Categories updated successfully."))
    except Exception as e:
        messages.error(
            request, _("Failed to update categories: %(error)s") % {"error": str(e)}
        )

    return redirect("project_setup_step", entity_pk=entity.pk, step=3)


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Product Templates
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_3_post(request, entity):
    """Assign product templates to entity."""
    if not entity:
        messages.error(request, _("Project not found."))
        return redirect("project_setup")

    if not request.user.is_staff:
        messages.error(
            request, _("You do not have permission to manage product templates.")
        )
        return redirect("project_setup_step", entity_pk=entity.pk, step=3)

    template_ids = request.POST.getlist("product_templates")

    try:
        with transaction.atomic():
            entity.product_templates.set(template_ids)
            if template_ids:
                messages.success(
                    request,
                    _("Product templates assigned successfully."),
                )
            else:
                messages.info(request, _("No product templates selected."))
    except Exception as e:
        messages.error(
            request, _("Failed to assign templates: %(error)s") % {"error": str(e)}
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
    if not entity:
        messages.error(request, _("Project not found."))
        return redirect("project_setup")

    selected_ids = request.POST.getlist("selected_entities")

    try:
        with transaction.atomic():
            for target_id in selected_ids:
                try:
                    target = Entity.objects.get(
                        pk=target_id, is_shareholder=True, active=True
                    )
                    Stakeholder.objects.get_or_create(
                        parent=entity,
                        target=target,
                        role="shareholder",
                    )
                except Entity.DoesNotExist:
                    pass

            if selected_ids:
                messages.success(request, _("Shareholders added successfully."))
            else:
                messages.info(request, _("No shareholders selected."))
    except Exception as e:
        messages.error(
            request, _("Failed to add shareholders: %(error)s") % {"error": str(e)}
        )

    messages.success(
        request, _("Project setup completed! Configure operations as needed.")
    )
    return redirect("entity_detail", pk=entity.pk)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Generic Stakeholder POST Handler
# ─────────────────────────────────────────────────────────────────────────────


def _handle_stakeholder_post(request, entity, role_type, next_step):
    """Generic handler for workers, vendors, and other stakeholders."""
    if not entity:
        messages.error(request, _("Project not found."))
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
        messages.error(request, _("Invalid role type."))
        return redirect("project_setup_step", entity_pk=entity.pk, step=next_step - 1)

    try:
        with transaction.atomic():
            for target_id in selected_ids:
                try:
                    target = Entity.objects.get(pk=target_id, **filter_kwargs)
                    Stakeholder.objects.get_or_create(
                        parent=entity,
                        target=target,
                        role=role_type,
                    )
                except Entity.DoesNotExist:
                    pass

            if selected_ids:
                messages.success(
                    request,
                    _("%(role)s added successfully.")
                    % {"role": role_type.capitalize()},
                )
            else:
                messages.info(request, _("No %(role)s selected.") % {"role": role_type})
    except Exception as e:
        messages.error(
            request,
            _("Failed to add %(role)s: %(error)s")
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
