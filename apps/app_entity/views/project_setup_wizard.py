"""Project setup wizard (create-only).

A function-based view (:func:`project_setup_wizard_view`) that walks through
seven steps — project info, financial categories, product templates, worker /
vendor / shareholder stakeholders, and a final summary — collecting each step's
data into a session draft. Nothing is persisted to the database until the user
confirms on the summary step.

The summary **Create** action applies the steps sequentially inside a single
``transaction.atomic()`` block. If any stage fails, the whole creation is rolled
back (no project is created) and the user is redirected back to the step whose
data failed, keeping the draft so they can correct it.
"""

from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext

from apps.app_base.logging_utils import audit_logger, build_error_details, logger
from apps.app_entity.models import (
    Entity,
    EntityType,
    Stakeholder,
)
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
    FinancialCategory,
)

from apps.app_inventory.models import ProductTemplate

SESSION_KEY = "project_setup_wizard"

STEPS = {
    1: {"name": "Project Info", "title": gettext("Initialize Project")},
    2: {"name": "Categories", "title": gettext("Financial Categories")},
    3: {"name": "Templates", "title": gettext("Product Templates")},
    4: {"name": "Workers", "title": gettext("Worker Stakeholders")},
    5: {"name": "Vendors", "title": gettext("Vendor Stakeholders")},
    6: {"name": "Shareholders", "title": gettext("Shareholder Stakeholders")},
    7: {"name": "Summary", "title": gettext("Review & Create")},
}

# Step numbers where each selection slice lives in the session draft.
_STAKEHOLDER_STEPS = (
    ("workers", "worker", 4),
    ("vendors", "vendor", 5),
    ("shareholders", "shareholder", 6),
)


# ─────────────────────────────────────────────────────────────────────────────
# Session draft helpers
# ─────────────────────────────────────────────────────────────────────────────


def _draft_get(request):
    """Return the current wizard draft (empty dict when none is started)."""
    return request.session.get(SESSION_KEY, {})


def _draft_save(request, data):
    """Persist the wizard draft to the session."""
    request.session[SESSION_KEY] = data
    request.session.modified = True


def _draft_clear(request):
    """Remove the wizard draft from the session."""
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True


def _default_info():
    """Sensible project-info defaults for a fresh (unstarted) draft."""
    return {
        "name": "",
        "description": "",
        "is_internal": False,
        "is_vendor": False,
        "is_client": False,
        "active": True,
    }


class _WizardStageError(Exception):
    """Creation failed while applying the data for a given wizard step."""

    def __init__(self, step, message):
        super().__init__(message)
        self.step = step


# ─────────────────────────────────────────────────────────────────────────────
# Main view + cancel
# ─────────────────────────────────────────────────────────────────────────────


def project_setup_wizard_view(request, step=1):
    """
    Create-only project setup wizard.

    - Steps 1-6 collect data into a session draft (no DB writes).
    - Step 7 (Summary) reviews the draft and its Create action commits the
      project atomically; on failure the user is redirected to the failing step.
    """
    logger.debug(
        f"Initializing project setup wizard | step={step} | "
        f"user={request.user.username}"
    )
    if step not in STEPS:
        logger.warning(f"Invalid wizard step | step={step}")
        audit_logger.info(
            f"wizard_invalid_step | ProjectSetupWizard:None | "
            f"user={request.user.username} | step={step}"
        )
        messages.error(request, gettext("Invalid wizard step."))
        return redirect("entity_list")

    draft = _draft_get(request)

    # Steps 2-7 require that the user started at step 1 (draft project info).
    if step > 1 and not (draft.get("info") or {}).get("name"):
        logger.warning(f"Wizard draft missing | step={step}")
        audit_logger.info(
            f"wizard_draft_missing | ProjectSetupWizard:None | "
            f"user={request.user.username} | step={step}"
        )
        messages.error(
            request,
            gettext("Session expired. Please start from the beginning."),
        )
        return redirect("project_create")

    if request.method == "POST":
        if step == 1:
            return _handle_step_1_post(request)
        elif step == 2:
            return _handle_step_2_post(request)
        elif step == 3:
            return _handle_step_3_post(request)
        elif step == 4:
            return _handle_stakeholder_post(request, "worker", "workers", 5)
        elif step == 5:
            return _handle_stakeholder_post(request, "vendor", "vendors", 6)
        elif step == 6:
            return _handle_stakeholder_post(
                request, "shareholder", "shareholders", 7
            )
        elif step == 7:
            return _handle_step_7_post(request)

    context = _get_step_context(request, step)
    context["step"] = step
    context["total_steps"] = len(STEPS)
    context["step_labels"] = STEPS
    context["step_nums"] = tuple(STEPS)
    logger.debug(f"Step {step} context built | user={request.user.username}")
    return render(request, "app_entity/project_setup_wizard.html", context)


def project_setup_cancel_view(request):
    """Abandon the wizard: clear the draft and return to the project list."""
    _draft_clear(request)
    audit_logger.info(
        f"wizard_cancelled | ProjectSetupWizard:None | "
        f"user={request.user.username}"
    )
    messages.info(request, gettext("Project setup cancelled."))
    return redirect("entity_list")


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Project Info (draft only)
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_1_post(request):
    """Validate and store the project-info draft (does NOT create the entity)."""
    logger.debug(
        f"Processing project info (step 1) | user={request.user.username}"
    )
    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "")
    is_internal = request.POST.get("is_internal") == "on"
    is_vendor = request.POST.get("is_vendor") == "on"
    is_client = request.POST.get("is_client") == "on"
    active = request.POST.get("active") == "on"

    if not name:
        logger.warning("Project name is required")
        audit_logger.info(
            f"wizard_step1_validation_failed | ProjectSetupWizard:None | "
            f"user={request.user.username} | reason=missing_name"
        )
        messages.error(request, gettext("Project name is required."))
        return redirect("project_create")

    draft = _draft_get(request)
    draft["info"] = {
        "name": name,
        "description": description,
        "is_internal": is_internal,
        "is_vendor": is_vendor,
        "is_client": is_client,
        "active": active,
    }
    _draft_save(request, draft)
    logger.debug(f"Project info stored in draft | name={name}")
    audit_logger.info(
        f"wizard_draft_step1_saved | ProjectSetupWizard:None | "
        f"user={request.user.username} | name={name}"
    )
    messages.success(
        request,
        gettext("Project details saved. Continue and review before creating."),
    )
    return redirect("project_setup", step=2)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Financial Categories (draft only)
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_2_post(request):
    """Store the selected category ids in the draft."""
    logger.debug(
        f"Processing financial categories (step 2) | "
        f"user={request.user.username}"
    )
    selected_pks = request.POST.getlist("selected_categories")
    try:
        selected_pks = sorted({int(pk) for pk in selected_pks if pk})
    except ValueError:
        logger.warning("Invalid category selection")
        audit_logger.info(
            f"wizard_step2_validation_failed | ProjectSetupWizard:None | "
            f"user={request.user.username} | reason=invalid_category_selection"
        )
        messages.error(request, gettext("Invalid category selection."))
        return redirect("project_setup", step=2)

    draft = _draft_get(request)
    draft["categories"] = selected_pks
    _draft_save(request, draft)
    logger.debug(
        f"Categories stored in draft | count={len(selected_pks)}"
    )
    audit_logger.info(
        f"wizard_draft_step2_saved | ProjectSetupWizard:None | "
        f"user={request.user.username} | count={len(selected_pks)}"
    )
    if selected_pks:
        messages.success(
            request,
            gettext("Category selection saved. Continue to product templates."),
        )
    else:
        messages.info(request, gettext("No categories selected — step skipped."))
    return redirect("project_setup", step=3)


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Product Templates (draft only, staff)
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_3_post(request):
    """Store the selected product templates in the draft (staff only)."""
    logger.debug(
        f"Processing product templates (step 3) | "
        f"user={request.user.username}"
    )
    if not request.user.is_staff:
        logger.warning(
            f"User lacks staff permission | user={request.user.username}"
        )
        audit_logger.info(
            f"wizard_step3_permission_denied | ProjectSetupWizard:None | "
            f"user={request.user.username} | reason=not_staff"
        )
        messages.error(
            request,
            gettext("You do not have permission to manage product templates."),
        )
        return redirect("project_setup", step=3)

    template_ids = request.POST.getlist("product_templates")
    try:
        template_ids = sorted({int(pk) for pk in template_ids if pk})
    except ValueError:
        logger.warning("Invalid template selection")
        messages.error(request, gettext("Invalid template selection."))
        return redirect("project_setup", step=3)

    draft = _draft_get(request)
    draft["templates"] = template_ids
    _draft_save(request, draft)
    logger.debug(
        f"Templates stored in draft | count={len(template_ids)}"
    )
    audit_logger.info(
        f"wizard_draft_step3_saved | ProjectSetupWizard:None | "
        f"user={request.user.username} | count={len(template_ids)}"
    )
    if template_ids:
        messages.success(
            request,
            gettext("Product template selection saved. Continue to workers."),
        )
    else:
        messages.info(request, gettext("No product templates selected — step skipped."))
    return redirect("project_setup", step=4)


# ─────────────────────────────────────────────────────────────────────────────
# Steps 4-6: Worker / Vendor / Shareholder stakeholders (draft only)
# ─────────────────────────────────────────────────────────────────────────────


def _handle_stakeholder_post(request, role_type, draft_key, next_step):
    """Store the selected stakeholder entity ids for *role_type* in the draft."""
    logger.debug(
        f"Processing {role_type} stakeholders (step {next_step - 1}) | "
        f"user={request.user.username}"
    )
    selected_ids = request.POST.getlist("selected_entities")
    try:
        selected_ids = sorted({int(pk) for pk in selected_ids if pk})
    except ValueError:
        messages.error(request, gettext("Invalid selection."))
        return redirect("project_setup", step=next_step - 1)

    draft = _draft_get(request)
    draft[draft_key] = selected_ids
    _draft_save(request, draft)
    logger.debug(
        f"{role_type} stakeholders stored in draft | count={len(selected_ids)}"
    )
    audit_logger.info(
        f"wizard_draft_step{next_step - 1}_saved | ProjectSetupWizard:None | "
        f"user={request.user.username} | role_type={role_type} | "
        f"count={len(selected_ids)}"
    )
    if selected_ids:
        messages.success(
            request,
            gettext("%(role)s selection saved.")
            % {"role": role_type.capitalize()},
        )
    else:
        messages.info(
            request,
            gettext("No %(role)s selected — step skipped.") % {"role": role_type},
        )
    return redirect("project_setup", step=next_step)


# ─────────────────────────────────────────────────────────────────────────────
# Step 7: Summary — atomic sequential create
# ─────────────────────────────────────────────────────────────────────────────


def _handle_step_7_post(request):
    """Create the project from the draft; redirect to the failing step on error."""
    logger.debug(
        f"Processing project creation (step 7 - Summary) | "
        f"user={request.user.username}"
    )
    try:
        entity = _apply_create_project(request)
    except _WizardStageError as exc:
        error_details = build_error_details(exc)
        logger.error(
            f"Project creation failed at step {exc.step} | "
            f"exception_type={error_details['exception_type']} | "
            f"error_message={error_details['error_message']}"
        )
        audit_logger.error(
            f"wizard_summary_create_failed | ProjectSetupWizard:None | "
            f"user={request.user.username} | step={exc.step} | "
            f"error={error_details}"
        )
        messages.error(request, str(exc))
        return redirect("project_setup", step=exc.step)
    except Exception as e:
        error_details = build_error_details(e)
        logger.error(
            f"Project creation failed | "
            f"exception_type={error_details['exception_type']} | "
            f"error_message={error_details['error_message']}"
        )
        audit_logger.error(
            f"wizard_summary_create_failed | ProjectSetupWizard:None | "
            f"user={request.user.username} | error={error_details}"
        )
        messages.error(
            request,
            gettext("Failed to create the project: %(error)s")
            % {"error": str(e)},
        )
        return redirect("project_setup", step=7)

    _draft_clear(request)
    logger.debug(
        f"Project setup completed | entity_id={entity.pk} | "
        f"project_name={entity.name}"
    )
    audit_logger.info(
        f"wizard_completed | ProjectSetupWizard:{entity.pk} | "
        f"user={request.user.username} | project_name={entity.name}"
    )
    messages.success(
        request,
        gettext("Project '%(name)s' created successfully.")
        % {"name": entity.name},
    )
    return redirect("entity_detail", pk=entity.pk)


def _apply_create_project(request):
    """Apply every step's draft data sequentially inside one atomic block.

    Runs in wizard order — project info, categories, templates, then worker /
    vendor / shareholder stakeholders. Any failure raises a
    :class:`_WizardStageError` carrying the failing step so the caller can
    redirect the user there; the enclosing transaction rolls back so nothing is
    created. Raises ``_WizardStageError`` on per-stage failures.
    """
    draft = _draft_get(request)
    info = draft.get("info") or _default_info()
    name = (info.get("name") or "").strip()
    if not name:
        raise _WizardStageError(1, gettext("Project name is required."))

    with transaction.atomic():
        # Stage A -> step 1: create the project entity.
        entity = Entity.create(
            entity_type=EntityType.PROJECT,
            name=name,
            description=info.get("description", ""),
            is_internal=bool(info.get("is_internal")),
            is_vendor=bool(info.get("is_vendor")),
            is_client=bool(info.get("is_client")),
            active=bool(info.get("active", True)),
        )
        audit_logger.info(
            f"wizard_project_created | ProjectSetupWizard:{entity.pk} | "
            f"user={request.user.username} | name={entity.name}"
        )

        # Stage B -> step 2: link the financial categories.
        try:
            _link_categories(entity, draft.get("categories", []))
        except _WizardStageError:
            raise
        except Exception as exc:
            raise _WizardStageError(
                2,
                gettext("Failed to link the selected categories: %(error)s")
                % {"error": str(exc)},
            ) from exc

        # Stage C -> step 3: assign the product templates (staff only).
        try:
            _assign_templates(request.user, entity, draft.get("templates", []))
        except _WizardStageError:
            raise
        except Exception as exc:
            raise _WizardStageError(
                3,
                gettext("Failed to assign the selected product templates: %(error)s")
                % {"error": str(exc)},
            ) from exc

        # Stage D -> steps 4-6: create the stakeholder links per role.
        for role_key, role, step in _STAKEHOLDER_STEPS:
            try:
                _create_stakeholders(entity, role, draft.get(role_key, []))
            except _WizardStageError:
                raise
            except Exception as exc:
                raise _WizardStageError(
                    step,
                    gettext("Failed to add the selected %(role)s: %(error)s")
                    % {"role": role, "error": str(exc)},
                ) from exc

    logger.debug(
        f"Project created from wizard draft | project_id={entity.pk}"
    )
    return entity


def _link_categories(entity, category_ids):
    """Create active category relations for the selected categories (step 2).

    Raises ``_WizardStageError`` (step 2) when a selected category no longer
    exists.
    """
    for category_id in category_ids:
        try:
            category = FinancialCategory.objects.get(pk=category_id)
        except FinancialCategory.DoesNotExist:
            raise _WizardStageError(
                2,
                gettext(
                    "A selected category no longer exists. Review the "
                    "financial categories step."
                ),
            )
        FinancialCategoriesEntitiesRelations.objects.get_or_create(
            entity=entity,
            category=category,
            defaults={
                "is_active": True,
                "max_limit": Decimal("0.00"),
            },
        )


def _assign_templates(user, entity, template_ids):
    """Assign the selected product templates to *entity* (step 3, staff only).

    Raises ``_WizardStageError`` (step 3) when a selected template no longer
    exists.
    """
    if not user.is_staff or not template_ids:
        return
    templates = list(ProductTemplate.objects.filter(pk__in=template_ids))
    if len(templates) != len(set(template_ids)):
        raise _WizardStageError(
            3,
            gettext(
                "A selected product template no longer exists. Review the "
                "product templates step."
            ),
        )
    entity.product_templates.set(templates)


def _role_filter(role_type):
    """Eligibility filter kwargs for a stakeholder role, or ``None`` if the
    role type is unknown."""
    if role_type == "worker":
        return {"is_worker": True, "active": True}
    if role_type == "vendor":
        return {"is_vendor": True, "active": True}
    if role_type == "shareholder":
        return {"is_shareholder": True, "active": True}
    return None


def _create_stakeholders(entity, role_type, selected_ids):
    """Create ``Stakeholder`` links on *entity* for the selected entity ids.

    Raises ``ValueError`` when a selected id no longer exists or is no longer
    eligible for the role. Returns the number of newly created links.
    """
    filter_kwargs = _role_filter(role_type)
    if filter_kwargs is None:
        raise ValueError(f"Invalid role type: {role_type}")
    created_count = 0
    for target_id in selected_ids:
        try:
            target = Entity.objects.get(pk=target_id, **filter_kwargs)
        except Entity.DoesNotExist:
            raise ValueError(
                gettext(
                    "A selected %(role)s no longer exists or is no longer "
                    "eligible for that role."
                )
                % {"role": role_type}
            )
        _, created = Stakeholder.objects.get_or_create(
            parent=entity,
            target=target,
            role=role_type,
        )
        if created:
            created_count += 1
    return created_count


# ─────────────────────────────────────────────────────────────────────────────
# GET Context Builders
# ─────────────────────────────────────────────────────────────────────────────


def _get_step_context(request, step):
    """Build the step context from the session draft (create-only wizard)."""
    draft = _draft_get(request)
    context = {"draft": draft}

    if step == 1:
        info = draft.get("info") or _default_info()
        context["draft_info"] = info
    elif step == 2:
        context.update(_step2_context(draft))
    elif step == 3:
        context.update(_step3_context(request.user, draft))
    elif step == 4:
        context.update(_stakeholder_context(draft, "worker"))
    elif step == 5:
        context.update(_stakeholder_context(draft, "vendor"))
    elif step == 6:
        context.update(_stakeholder_context(draft, "shareholder"))
    elif step == 7:
        context.update(_summary_context(draft))
    return context


def _step2_context(draft):
    """Step 2 context: all categories grouped by aspect, with draft selections."""
    available_by_aspect = {}
    categories = FinancialCategory.objects.order_by("aspect", "name")
    for category in categories:
        available_by_aspect.setdefault(category.aspect, []).append(category)

    return {
        "available_by_aspect": available_by_aspect,
        "linked_by_aspect": {},
        "selected_category_ids": set(draft.get("categories", [])),
    }


def _step3_context(user, draft):
    """Step 3 context: product templates with the draft selections highlighted."""
    enabled_ids = set(draft.get("templates", []))
    if user.is_staff:
        templates = ProductTemplate.objects.all().order_by(
            "nature", "sub_category", "name"
        )
    else:
        templates = ProductTemplate.objects.none()
    return {"templates": templates, "enabled_ids": enabled_ids}


def _stakeholder_context(draft, role):
    """Eligible entities + draft-selected stakeholder ids for a role."""
    role_key = {"worker": "workers", "vendor": "vendors", "shareholder": "shareholders"}[
        role
    ]
    filter_kwargs = _role_filter(role)
    if filter_kwargs:
        eligible = Entity.objects.filter(**filter_kwargs).order_by("name")
    else:
        eligible = Entity.objects.none()
    selected = set(draft.get(role_key, []))
    return {
        "eligible_entities": eligible,
        "existing_stakeholder_ids": selected,
    }


def _summary_context(draft):
    """Step 7 context: read-only summary of everything collected in the draft."""
    info = draft.get("info") or _default_info()

    category_ids = draft.get("categories", [])
    categories = list(
        FinancialCategory.objects.filter(id__in=category_ids).order_by("aspect", "name")
    )

    template_ids = draft.get("templates", [])
    templates = list(
        ProductTemplate.objects.filter(id__in=template_ids).order_by("nature", "name")
    )

    role_entities = {}
    for role_key, role, _step in _STAKEHOLDER_STEPS:
        ids = draft.get(role_key, [])
        role_entities[role] = list(
            Entity.objects.filter(id__in=ids).order_by("name")
        )

    return {
        "summary_info": info,
        "summary_categories": categories,
        "summary_templates": templates,
        "summary_workers": role_entities["worker"],
        "summary_vendors": role_entities["vendor"],
        "summary_shareholders": role_entities["shareholder"],
        "summary_counts": {
            "categories": len(category_ids),
            "templates": len(template_ids),
            "workers": len(role_entities["worker"]),
            "vendors": len(role_entities["vendor"]),
            "shareholders": len(role_entities["shareholder"]),
        },
    }
