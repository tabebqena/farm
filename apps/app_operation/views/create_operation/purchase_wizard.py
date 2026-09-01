from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import ProductTemplate
from apps.app_operation.forms import (
    PurchaseItemForm,
    PurchaseWizardStep1Form,
    PurchaseWizardStep2Form,
    PurchaseWizardStep3Form,
)
from apps.app_operation.models import PurchaseOperation
from farm.shortcuts import get_object_or_404

from .wizard_base import Wizard

# ---------------------------------------------------------------------------
# Wizard config
# ---------------------------------------------------------------------------

STEPS = {
    1: {"name": _("Basic Info"), "title": _("Purchase — Basic Information")},
    2: {"name": _("Total Amount"), "title": _("Purchase — Invoice Total")},
    3: {"name": _("Payment"), "title": _("Purchase — Payment (optional)")},
}

PURCHASE_WIZARD = Wizard(
    prefix="purchase_wizard",
    steps=STEPS,
    counterpart_field="vendor",
    step1_form_class=PurchaseWizardStep1Form,
    step2_form_class=PurchaseWizardStep2Form,
    step3_form_class=PurchaseWizardStep3Form,
    step1_url="purchase_wizard_step1",
    step_new_url="purchase_wizard_step_new",
    invoice_url="purchase_invoice",
    cancel_url="purchase_wizard_cancel",
    submit_url="purchase_submit",
    template_name="app_operation/purchase_wizard.html",
    invoice_template_name="app_operation/purchase_invoice.html",
    recorded_message=_("Purchase recorded successfully."),
)


# ---------------------------------------------------------------------------
# Project guard
# ---------------------------------------------------------------------------


def _load_project(request, pk):
    """Return (project, None) or (None, redirect_response)."""
    project = get_object_or_404(
        Entity,
        pk=pk,
        entity_type=EntityType.PROJECT,
        error_message="Project not found or has been deleted.",
    )
    vendor_count = Stakeholder.objects.filter(
        parent=project, role=StakeholderRole.VENDOR, active=True
    ).count()
    if vendor_count == 0:
        messages.warning(
            request,
            _("Cannot create purchase: no active vendors configured for this project."),
        )
        return None, redirect("operation_list_view", person_pk=pk)
    return project, None


# ---------------------------------------------------------------------------
# Cancel / steps
# ---------------------------------------------------------------------------


def cancel_purchase_wizard_view(request, pk):
    return PURCHASE_WIZARD.cancel(request, pk)


def purchase_wizard_view(request, pk, step=1):
    project, redir = _load_project(request, pk)
    if redir:
        return redir
    return PURCHASE_WIZARD.handle_wizard(request, pk, step, project)


# ---------------------------------------------------------------------------
# Invoice hub
# ---------------------------------------------------------------------------


def purchase_invoice_view(request, pk):
    project, redir = _load_project(request, pk)
    if redir:
        return redir

    def augment_item(item):
        try:
            template = ProductTemplate.objects.get(pk=item["product_template_id"])
            template_name = template.name
        except ProductTemplate.DoesNotExist:
            template_name = _("(unknown)")
        return {"template_name": template_name}

    return PURCHASE_WIZARD.render_invoice(request, pk, project, augment_item)


# ---------------------------------------------------------------------------
# Select template
# ---------------------------------------------------------------------------


def purchase_select_template_view(request, pk):
    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = PURCHASE_WIZARD.get_session(request, pk)
    if "total_amount" not in session:
        messages.error(request, _("Session expired. Please start from the beginning."))
        return redirect("purchase_wizard_step1", pk=pk)

    templates = ProductTemplate.objects.filter(entities=project).order_by(
        "nature", "name"
    )
    return render(
        request,
        "app_operation/purchase_select_template.html",
        {
            "project": project,
            "templates": templates,
        },
    )


# ---------------------------------------------------------------------------
# Add / edit item
# ---------------------------------------------------------------------------


def purchase_add_item_view(request, pk, idx=None):
    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = PURCHASE_WIZARD.get_session(request, pk)
    if "total_amount" not in session:
        messages.error(request, _("Session expired. Please start from the beginning."))
        return redirect("purchase_wizard_step1", pk=pk)

    items = session.setdefault("items", [])
    is_edit = idx is not None

    # Resolve template
    if request.method == "POST":
        try:
            template_pk = int(request.POST.get("product_template_id", 0))
        except (ValueError, TypeError):
            messages.error(request, _("Invalid product template."))
            return redirect("purchase_select_template", pk=pk)
    elif is_edit:
        if idx < 0 or idx >= len(items):
            messages.warning(request, _("Item not found."))
            return redirect("purchase_invoice", pk=pk)
        template_pk = items[idx]["product_template_id"]
    else:
        try:
            template_pk = int(request.GET.get("template_id", 0))
        except (ValueError, TypeError):
            template_pk = 0

    template = get_object_or_404(
        ProductTemplate,
        pk=template_pk,
        entities=project,
        error_message="Product template not found or is not assigned to this project.",
    )

    if request.method == "POST":
        form = PurchaseItemForm(request.POST, template=template, entity=project)
        if form.is_valid():
            cd = form.cleaned_data
            # Duplicate unique_id guard (auto-suggested tags are unique by
            # construction; only explicit user-typed tags need this check)
            uid = (cd.get("unique_id") or "").strip()
            if (
                uid
                and template.tracking_mode == ProductTemplate.TrackingMode.INDIVIDUAL
            ):
                for i, existing in enumerate(items):
                    if i == idx:
                        continue
                    if (
                        existing["product_template_id"] == template.pk
                        and existing.get("unique_id") == uid
                    ):
                        form.add_error(
                            "unique_id",
                            _("This Tag/ID is already used by another item."),
                        )
                        break

        if form.is_valid():
            cd = form.cleaned_data
            item_data = {
                "idx": idx if is_edit else len(items),
                "product_template_id": template.pk,
                "description": cd.get("description", ""),
                "quantity": str(cd["quantity"]),
                "unit_price": str(cd["unit_price"]),
                "unique_id": (cd.get("unique_id") or "").strip(),
                "received_qty": str(cd["received_qty"]),
            }
            if is_edit:
                items[idx] = item_data
            else:
                items.append(item_data)
            PURCHASE_WIZARD.save_session(request, project.pk, session)
            return redirect("purchase_invoice", pk=pk)
    else:
        if is_edit:
            item = items[idx]
            initial = {
                "product_template_id": template.pk,
                "description": item.get("description", ""),
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "unique_id": item.get("unique_id", ""),
                "received_qty": item.get("received_qty", "0"),
            }
        else:
            initial = {"product_template_id": template.pk, "received_qty": "0"}
        form = PurchaseItemForm(
            initial=initial, template=template, entity=project
        )

    return render(
        request,
        "app_operation/purchase_add_item.html",
        {
            "project": project,
            "form": form,
            "template": template,
            "is_edit": is_edit,
            "idx": idx,
        },
    )


# ---------------------------------------------------------------------------
# Delete item
# ---------------------------------------------------------------------------


def purchase_delete_item_view(request, pk, idx):
    return PURCHASE_WIZARD.delete_item(request, pk, idx)


# ---------------------------------------------------------------------------
# Final submit
# ---------------------------------------------------------------------------


def _do_submit(request, project, session_data):
    """Delegate to PurchaseOperation.create_from_session()."""
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        return PurchaseOperation.create_from_session(
            project=project,
            session_data=session_data,
            officer=request.user,
        )


def purchase_submit_view(request, pk):
    if request.method != "POST":
        return redirect("purchase_invoice", pk=pk)

    project, redir = _load_project(request, pk)
    if redir:
        return redir

    return PURCHASE_WIZARD.submit(request, pk, project, _do_submit)
