import logging
from datetime import date, datetime
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from farm.shortcuts import get_object_or_404
from apps.app_base.debug import DebugContext, debug_view
from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InventoryMovement,
    InventoryMovementLine,
    Product,
    ProductTemplate,
)
from apps.app_operation.forms import (
    PurchaseItemForm,
    PurchaseWizardStep1Form,
    PurchaseWizardStep2Form,
    PurchaseWizardStep3Form,
)
from apps.app_operation.models import PurchaseOperation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _session_key(project_pk):
    return f"purchase_wizard_{project_pk}"


def _get_session(request, project_pk) -> dict:
    return request.session.get(_session_key(project_pk), {})


def _save_session(request, project_pk, data: dict):
    request.session[_session_key(project_pk)] = data
    request.session.modified = True


def _clear_session(request, project_pk):
    key = _session_key(project_pk)
    request.session.pop(key, None)
    request.session.modified = True


def _items_total(items: list) -> Decimal:
    return sum(
        Decimal(item["quantity"]) * Decimal(item["unit_price"]) for item in items
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
        error_message="Project not found or has been deleted."
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
# Cancel
# ---------------------------------------------------------------------------

def cancel_purchase_wizard_view(request, pk):
    _clear_session(request, pk)
    return redirect("operation_list_view", person_pk=pk)


# ---------------------------------------------------------------------------
# Wizard steps 1–3  (session-only, nothing written to DB)
# ---------------------------------------------------------------------------

STEPS = {
    1: {"name": _("Basic Info"),    "title": _("Purchase — Basic Information")},
    2: {"name": _("Total Amount"),  "title": _("Purchase — Invoice Total")},
    3: {"name": _("Payment"),       "title": _("Purchase — Payment (optional)")},
}


@debug_view
def purchase_wizard_view(request, pk, step=1):
    if step not in STEPS:
        messages.error(request, _("Invalid wizard step."))
        return redirect("operation_list_view", person_pk=pk)

    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = _get_session(request, pk)

    # Steps 2-3 require step 1 session data
    if step >= 2 and "date" not in session:
        messages.error(request, _("Session expired. Please start from the beginning."))
        return redirect("purchase_wizard_step1", pk=pk)

    if request.method == "POST":
        if step == 1:
            return _handle_step_1_post(request, project, session)
        elif step == 2:
            return _handle_step_2_post(request, project, session)
        elif step == 3:
            return _handle_step_3_post(request, project, session)

    # GET
    next_param = request.GET.get("next", "")
    context = {"project": project, "step": step, "steps": STEPS, "current_step": STEPS[step], "next_param": next_param}

    if step == 1:
        initial = {
            "date": session.get("date", date.today().isoformat()),
            "vendor": session.get("vendor_id"),
            "description": session.get("description", ""),
        }
        context["form"] = PurchaseWizardStep1Form(initial=initial, project=project)

    elif step == 2:
        initial = {"total_amount": session.get("total_amount")}
        context["form"] = PurchaseWizardStep2Form(initial=initial)
        context["step1_data"] = _resolve_step1_display(session)

    elif step == 3:
        initial = {"amount_paid": session.get("amount_paid") or ""}
        context["form"] = PurchaseWizardStep3Form(initial=initial)
        context["total_amount"] = session.get("total_amount")

    return render(request, "app_operation/purchase_wizard.html", context)


def _resolve_step1_display(session: dict) -> dict:
    """Return step 1 values suitable for read-only display."""
    vendor = None
    if session.get("vendor_id"):
        try:
            vendor = Entity.objects.get(pk=session["vendor_id"])
        except Entity.DoesNotExist:
            pass
    return {"date": session.get("date", ""), "vendor": vendor, "description": session.get("description", "")}


def _handle_step_1_post(request, project, session: dict):
    form = PurchaseWizardStep1Form(request.POST, project=project)
    if not form.is_valid():
        return render(request, "app_operation/purchase_wizard.html", {
            "project": project, "step": 1, "steps": STEPS,
            "current_step": STEPS[1], "form": form,
        })
    session.update({
        "date": form.cleaned_data["date"].isoformat(),
        "vendor_id": form.cleaned_data["vendor"].pk,
        "description": form.cleaned_data["description"],
        "items": session.get("items", []),
    })
    _save_session(request, project.pk, session)
    return redirect("purchase_wizard_step_new", pk=project.pk, step=2)


def _handle_step_2_post(request, project, session: dict):
    next_param = request.POST.get("next", "")
    form = PurchaseWizardStep2Form(request.POST)
    if not form.is_valid():
        return render(request, "app_operation/purchase_wizard.html", {
            "project": project, "step": 2, "steps": STEPS,
            "current_step": STEPS[2], "form": form,
            "step1_data": _resolve_step1_display(session),
            "next_param": next_param,
        })
    session["total_amount"] = str(form.cleaned_data["total_amount"])
    _save_session(request, project.pk, session)
    if next_param == "invoice":
        return redirect("purchase_invoice", pk=project.pk)
    return redirect("purchase_wizard_step_new", pk=project.pk, step=3)


def _handle_step_3_post(request, project, session: dict):
    next_param = request.POST.get("next", "")
    form = PurchaseWizardStep3Form(request.POST)
    if not form.is_valid():
        return render(request, "app_operation/purchase_wizard.html", {
            "project": project, "step": 3, "steps": STEPS,
            "current_step": STEPS[3], "form": form,
            "total_amount": session.get("total_amount"),
            "next_param": next_param,
        })
    paid = form.cleaned_data["amount_paid"]
    total = Decimal(session["total_amount"])
    if paid > total:
        form.add_error("amount_paid", _("Payment cannot exceed the declared total."))
        return render(request, "app_operation/purchase_wizard.html", {
            "project": project, "step": 3, "steps": STEPS,
            "current_step": STEPS[3], "form": form,
            "total_amount": session.get("total_amount"),
            "next_param": next_param,
        })
    session["amount_paid"] = str(paid)
    _save_session(request, project.pk, session)
    return redirect("purchase_invoice", pk=project.pk)


# ---------------------------------------------------------------------------
# Invoice hub
# ---------------------------------------------------------------------------

@debug_view
def purchase_invoice_view(request, pk):
    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = _get_session(request, pk)
    if "total_amount" not in session:
        messages.error(request, _("Session expired. Please start from the beginning."))
        return redirect("purchase_wizard_step1", pk=pk)

    total_amount = Decimal(session["total_amount"])
    raw_items = session.get("items", [])

    # Augment each item with display fields
    items = []
    for item in raw_items:
        try:
            template = ProductTemplate.objects.get(pk=item["product_template_id"])
            template_name = template.name
        except ProductTemplate.DoesNotExist:
            template_name = _("(unknown)")
        qty = Decimal(item["quantity"])
        price = Decimal(item["unit_price"])
        items.append({**item, "template_name": template_name, "total_price": qty * price})

    items_total = _items_total(raw_items)
    difference = total_amount - items_total
    submit_enabled = abs(difference) <= Decimal("0.01")

    vendor = _resolve_step1_display(session).get("vendor")

    return render(request, "app_operation/purchase_invoice.html", {
        "project": project,
        "session_data": session,
        "items": items,
        "items_total": items_total,
        "difference": difference,
        "submit_enabled": submit_enabled,
        "vendor": vendor,
    })


# ---------------------------------------------------------------------------
# Select template
# ---------------------------------------------------------------------------

@debug_view
def purchase_select_template_view(request, pk):
    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = _get_session(request, pk)
    if "total_amount" not in session:
        messages.error(request, _("Session expired. Please start from the beginning."))
        return redirect("purchase_wizard_step1", pk=pk)

    templates = ProductTemplate.objects.filter(entities=project).order_by("nature", "name")
    return render(request, "app_operation/purchase_select_template.html", {
        "project": project,
        "templates": templates,
    })


# ---------------------------------------------------------------------------
# Add / edit item
# ---------------------------------------------------------------------------

@debug_view
def purchase_add_item_view(request, pk, idx=None):
    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = _get_session(request, pk)
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
        error_message="Product template not found or is not assigned to this project."
    )

    if request.method == "POST":
        form = PurchaseItemForm(request.POST, template=template)
        if form.is_valid():
            cd = form.cleaned_data
            # Duplicate unique_id guard
            uid = (cd.get("unique_id") or "").strip()
            if uid and template.requires_individual_tag:
                for i, existing in enumerate(items):
                    if i == idx:
                        continue
                    if (existing["product_template_id"] == template.pk
                            and existing.get("unique_id") == uid):
                        form.add_error("unique_id", _("This Tag/ID is already used by another item."))
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
            _save_session(request, project.pk, session)
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
        form = PurchaseItemForm(initial=initial, template=template)

    return render(request, "app_operation/purchase_add_item.html", {
        "project": project,
        "form": form,
        "template": template,
        "is_edit": is_edit,
        "idx": idx,
    })


# ---------------------------------------------------------------------------
# Delete item
# ---------------------------------------------------------------------------

def purchase_delete_item_view(request, pk, idx):
    if request.method != "POST":
        return redirect("purchase_invoice", pk=pk)

    session = _get_session(request, pk)
    items = session.get("items", [])
    if 0 <= idx < len(items):
        items = [item for i, item in enumerate(items) if i != idx]
        for i, item in enumerate(items):
            item["idx"] = i
        session["items"] = items
        _save_session(request, pk, session)
    return redirect("purchase_invoice", pk=pk)


# ---------------------------------------------------------------------------
# Final submit
# ---------------------------------------------------------------------------

def purchase_submit_view(request, pk):
    if request.method != "POST":
        return redirect("purchase_invoice", pk=pk)

    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = _get_session(request, pk)
    if "total_amount" not in session:
        messages.error(request, _("Session expired. Please start from the beginning."))
        return redirect("purchase_wizard_step1", pk=pk)

    items = session.get("items", [])
    if not items:
        messages.error(request, _("Add at least one item before submitting."))
        return redirect("purchase_invoice", pk=pk)

    try:
        op = _do_submit(request, project, session)
    except Exception as e:
        logger.exception("Error during purchase submit")
        messages.error(request, _("Error: %(e)s") % {"e": str(e)})
        return redirect("purchase_invoice", pk=pk)

    _clear_session(request, pk)
    messages.success(request, _("Purchase recorded successfully."))
    return redirect("operation_detail_view", pk=op.pk)


@transaction.atomic
def _do_submit(request, project, session_data: dict):
    date_val = datetime.fromisoformat(session_data["date"]).date()
    vendor = get_object_or_404(
        Entity,
        pk=session_data["vendor_id"],
        error_message="Vendor not found or has been deleted."
    )
    desc = session_data.get("description", "")
    total = Decimal(session_data["total_amount"])
    paid = Decimal(session_data.get("amount_paid", "0"))
    items = session_data["items"]

    # Integrity check
    computed = _items_total(items)
    if abs(computed - total) > Decimal("0.01"):
        raise ValueError(
            _("Items total %(items)s does not match declared total %(total)s.")
            % {"items": computed, "total": total}
        )

    # 1. Create operation
    op = PurchaseOperation.objects.create(
        source=project,
        destination=vendor,
        amount=total,
        date=date_val,
        description=desc,
        officer=request.user,
        operation_type="PURCHASE",
    )

    movement_lines = []

    for item_data in items:
        template = get_object_or_404(
            ProductTemplate,
            pk=item_data["product_template_id"],
            error_message="Product template not found or has been deleted."
        )

        # 2. Create InvoiceItem
        from apps.app_inventory.models import InvoiceItem
        invoice_item = InvoiceItem.objects.create(
            operation=op,
            product=template,
            description=item_data.get("description", ""),
            quantity=Decimal(item_data["quantity"]),
            unit_price=Decimal(item_data["unit_price"]),
        )

        # 3. Create Product and link via M2M (replicates save_inventory PURCHASE branch)
        uid = (item_data.get("unique_id") or "").strip() or None
        product = Product.objects.create(
            entity=vendor,
            product_template=template,
            quantity=Decimal(item_data["quantity"]),
            unit_price=Decimal(item_data["unit_price"]),
            unique_id=uid,
        )
        product.invoice_items.add(invoice_item)

        received_qty = Decimal(item_data.get("received_qty", "0"))
        if received_qty > Decimal("0"):
            movement_lines.append((invoice_item, received_qty))

    # 4. InventoryMovement if any received quantities
    if movement_lines:
        movement = InventoryMovement.objects.create(
            operation=op,
            date=date_val,
            officer=request.user,
            notes="",
        )
        for invoice_item, received_qty in movement_lines:
            InventoryMovementLine.objects.create(
                movement=movement,
                invoice_item=invoice_item,
                quantity=received_qty,
            )

    # 5. Payment transaction
    if paid > Decimal("0"):
        op.create_payment_transaction(
            amount=paid,
            officer=request.user,
            date=date_val,
            description=_("Payment for Purchase #%(pk)s") % {"pk": op.pk},
        )

    DebugContext.success("Purchase submitted", {"operation_pk": op.pk})
    return op
