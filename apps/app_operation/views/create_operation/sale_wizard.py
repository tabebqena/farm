import logging
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.app_base.debug import debug_view
from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import Product
from apps.app_inventory.stock import movement_state, portfolio as stock_portfolio
from apps.app_operation.forms import (
    SaleItemForm,
    SaleWizardStep1Form,
    SaleWizardStep2Form,
    SaleWizardStep3Form,
)
from apps.app_operation.models import SaleOperation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def _session_key(project_pk):
    return f"sale_wizard_{project_pk}"


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


def _get_project_product(project, product_id):
    """Return a product owned by *project*, or None."""
    if not product_id:
        return None
    try:
        return Product.objects.get(pk=product_id, entity=project)
    except Product.DoesNotExist:
        return None


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
    # Commented because it is weired, 
    # The user can see warning & link to click instead.
    # client_count = Stakeholder.objects.filter(
    #     parent=project, role=StakeholderRole.CLIENT, active=True
    # ).count()
    # if client_count == 0:
    #     messages.warning(
    #         request,
    #         _("Cannot create sale: no active clients configured for this project."),
    #     )
    #     return None, redirect("operation_list_view", person_pk=pk)
    return project, None


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def cancel_sale_wizard_view(request, pk):
    _clear_session(request, pk)
    return redirect("operation_list_view", person_pk=pk)


# ---------------------------------------------------------------------------
# Wizard steps 1–3  (session-only, nothing written to DB)
# ---------------------------------------------------------------------------

STEPS = {
    1: {"name": _("Basic Info"), "title": _("Sale — Basic Information")},
    2: {"name": _("Total Amount"), "title": _("Sale — Invoice Total")},
    3: {"name": _("Payment"), "title": _("Sale — Payment (optional)")},
}


@debug_view
def sale_wizard_view(request, pk, step=1):
    # TODO: not fully implemented
    # Need to match the purchase_wizard & delegeate logics to the models
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
        return redirect("sale_wizard_step1", pk=pk)

    if request.method == "POST":
        if step == 1:
            return _handle_step_1_post(request, project, session)
        elif step == 2:
            return _handle_step_2_post(request, project, session)
        elif step == 3:
            return _handle_step_3_post(request, project, session)

    # GET
    next_param = request.GET.get("next", "")
    context = {
        "project": project,
        "step": step,
        "steps": STEPS,
        "current_step": STEPS[step],
        "next_param": next_param,
    }

    if step == 1:
        initial = {
            "date": session.get("date", date.today().isoformat()),
            "client": session.get("client_id"),
            "description": session.get("description", ""),
        }
        context["form"] = SaleWizardStep1Form(initial=initial, project=project)

    elif step == 2:
        initial = {"total_amount": session.get("total_amount")}
        context["form"] = SaleWizardStep2Form(initial=initial)
        context["step1_data"] = _resolve_step1_display(session)

    elif step == 3:
        initial = {"amount_paid": session.get("amount_paid") or ""}
        context["form"] = SaleWizardStep3Form(initial=initial)
        context["total_amount"] = session.get("total_amount")

    return render(request, "app_operation/sale_wizard.html", context)


def _resolve_step1_display(session: dict) -> dict:
    """Return step 1 values suitable for read-only display."""
    client = None
    if session.get("client_id"):
        try:
            client = Entity.objects.get(pk=session["client_id"])
        except Entity.DoesNotExist:
            pass
    return {
        "date": session.get("date", ""),
        "client": client,
        "description": session.get("description", ""),
    }


def _handle_step_1_post(request, project, session: dict):
    form = SaleWizardStep1Form(request.POST, project=project)
    if not form.is_valid():
        return render(
            request,
            "app_operation/sale_wizard.html",
            {
                "project": project,
                "step": 1,
                "steps": STEPS,
                "current_step": STEPS[1],
                "form": form,
            },
        )
    session.update(
        {
            "date": form.cleaned_data["date"].isoformat(),
            "client_id": form.cleaned_data["client"].pk,
            "description": form.cleaned_data["description"],
            "items": session.get("items", []),
        }
    )
    _save_session(request, project.pk, session)
    return redirect("sale_wizard_step_new", pk=project.pk, step=2)


def _handle_step_2_post(request, project, session: dict):
    next_param = request.POST.get("next", "")
    form = SaleWizardStep2Form(request.POST)
    if not form.is_valid():
        return render(
            request,
            "app_operation/sale_wizard.html",
            {
                "project": project,
                "step": 2,
                "steps": STEPS,
                "current_step": STEPS[2],
                "form": form,
                "step1_data": _resolve_step1_display(session),
                "next_param": next_param,
            },
        )
    session["total_amount"] = str(form.cleaned_data["total_amount"])
    _save_session(request, project.pk, session)
    if next_param == "invoice":
        return redirect("sale_invoice", pk=project.pk)
    return redirect("sale_wizard_step_new", pk=project.pk, step=3)


def _handle_step_3_post(request, project, session: dict):
    next_param = request.POST.get("next", "")
    form = SaleWizardStep3Form(request.POST)
    if not form.is_valid():
        return render(
            request,
            "app_operation/sale_wizard.html",
            {
                "project": project,
                "step": 3,
                "steps": STEPS,
                "current_step": STEPS[3],
                "form": form,
                "total_amount": session.get("total_amount"),
                "next_param": next_param,
            },
        )
    paid = form.cleaned_data["amount_paid"]
    total = Decimal(session["total_amount"])
    if paid > total:
        form.add_error("amount_paid", _("Payment cannot exceed the declared total."))
        return render(
            request,
            "app_operation/sale_wizard.html",
            {
                "project": project,
                "step": 3,
                "steps": STEPS,
                "current_step": STEPS[3],
                "form": form,
                "total_amount": session.get("total_amount"),
                "next_param": next_param,
            },
        )
    session["amount_paid"] = str(paid)
    _save_session(request, project.pk, session)
    return redirect("sale_invoice", pk=project.pk)


# ---------------------------------------------------------------------------
# Invoice hub
# ---------------------------------------------------------------------------


@debug_view
def sale_invoice_view(request, pk):
    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = _get_session(request, pk)
    if "total_amount" not in session:
        messages.error(request, _("Session expired. Please start from the beginning."))
        return redirect("sale_wizard_step1", pk=pk)

    total_amount = Decimal(session["total_amount"])
    raw_items = session.get("items", [])

    # Augment each item with display fields (product-based)
    items = []
    for item in raw_items:
        product = _get_project_product(project, item.get("product_id"))
        if product is not None:
            template_name = product.product_template.name
            tag = product.unique_id or ""
        else:
            template_name = _("(unknown)")
            tag = ""
        qty = Decimal(item["quantity"])
        price = Decimal(item["unit_price"])
        items.append(
            {
                **item,
                "template_name": template_name,
                "tag": tag,
                "total_price": qty * price,
            }
        )

    items_total = _items_total(raw_items)
    difference = total_amount - items_total
    submit_enabled = abs(difference) <= Decimal("0.01")

    client = _resolve_step1_display(session).get("client")

    return render(
        request,
        "app_operation/sale_invoice.html",
        {
            "project": project,
            "session_data": session,
            "items": items,
            "items_total": items_total,
            "difference": difference,
            "submit_enabled": submit_enabled,
            "client": client,
        },
    )


# ---------------------------------------------------------------------------
# Select template
# ---------------------------------------------------------------------------


@debug_view
def sale_select_product_view(request, pk):
    """List the seller's EXISTING on-hand products to pick for the sale."""
    from datetime import date

    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = _get_session(request, pk)
    if "total_amount" not in session:
        messages.error(request, _("Session expired. Please start from the beginning."))
        return redirect("sale_wizard_step1", pk=pk)

    # Physically-present products owned by the project (the seller's stock).
    portfolio_rows = list(stock_portfolio(project, date.today()))
    portfolio = {r["product_id"]: r["quantity"] for r in portfolio_rows}
    product_ids = list(portfolio.keys())
    products = (
        Product.objects.filter(entity=project, pk__in=product_ids)
        .select_related("product_template")
        .order_by("product_template__nature", "product_template__name", "pk")
    )

    # Group by template; only ACTIVE products are sellable.
    by_template: dict = {}
    for p in products:
        if p.status != Product.Status.ACTIVE:
            continue
        by_template.setdefault(p.product_template, []).append(
            {"product": p, "available": portfolio[p.pk]}
        )
    templates = sorted(by_template.items(), key=lambda kv: (kv[0].nature, kv[0].name))

    return render(
        request,
        "app_operation/sale_select_product.html",
        {
            "project": project,
            "templates": templates,
        },
    )


# ---------------------------------------------------------------------------
# Add / edit item
# ---------------------------------------------------------------------------


@debug_view
def sale_add_item_view(request, pk, idx=None):
    """Add/edit a sale invoice item by selecting an EXISTING product from stock."""
    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = _get_session(request, pk)
    if "total_amount" not in session:
        messages.error(request, _("Session expired. Please start from the beginning."))
        return redirect("sale_wizard_step1", pk=pk)

    items = session.setdefault("items", [])
    is_edit = idx is not None

    if request.method == "POST":
        try:
            product_id = int(request.POST.get("product_id", 0))
        except (ValueError, TypeError):
            product_id = 0
        product = _get_project_product(project, product_id)
        if product is None:
            messages.error(request, _("Please choose a product from your stock."))
            return redirect("sale_select_product", pk=pk)
        form = SaleItemForm(request.POST, product=product, entity=project)
        if form.is_valid():
            cd = form.cleaned_data
            item_data = {
                "idx": idx if is_edit else len(items),
                "product_id": product.pk,
                "description": cd.get("description", ""),
                "quantity": str(cd["quantity"]),
                "unit_price": str(cd["unit_price"]),
            }
            if is_edit:
                items[idx] = item_data
            else:
                items.append(item_data)
            _save_session(request, project.pk, session)
            return redirect("sale_invoice", pk=pk)
    else:
        if is_edit:
            if idx < 0 or idx >= len(items):
                messages.warning(request, _("Item not found."))
                return redirect("sale_invoice", pk=pk)
            item = items[idx]
            product = _get_project_product(project, item.get("product_id"))
            if product is None:
                messages.error(
                    request,
                    _("Selected product not found or is no longer available."),
                )
                return redirect("sale_invoice", pk=pk)
            initial = {
                "product_id": product.pk,
                "description": item.get("description", ""),
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
            }
        else:
            try:
                product_id = int(request.GET.get("product_id", 0))
            except (ValueError, TypeError):
                product_id = 0
            product = _get_project_product(project, product_id)
            if product is None:
                messages.error(request, _("Please choose a product from your stock."))
                return redirect("sale_select_product", pk=pk)
            initial = {
                "product_id": product.pk,
                "quantity": "1",
                "unit_price": str(product.unit_price),
            }
        form = SaleItemForm(initial=initial, product=product, entity=project)

    from datetime import date

    available = movement_state(product, as_of=date.today())["quantity"]
    return render(
        request,
        "app_operation/sale_add_item.html",
        {
            "project": project,
            "form": form,
            "product": product,
            "available": available,
            "is_edit": is_edit,
            "idx": idx,
        },
    )


# ---------------------------------------------------------------------------
# Delete item
# ---------------------------------------------------------------------------


def sale_delete_item_view(request, pk, idx):
    if request.method != "POST":
        return redirect("sale_invoice", pk=pk)

    session = _get_session(request, pk)
    items = session.get("items", [])
    if 0 <= idx < len(items):
        items = [item for i, item in enumerate(items) if i != idx]
        for i, item in enumerate(items):
            item["idx"] = i
        session["items"] = items
        _save_session(request, pk, session)
    return redirect("sale_invoice", pk=pk)


# ---------------------------------------------------------------------------
# Final submit
# ---------------------------------------------------------------------------


def sale_submit_view(request, pk):
    if request.method != "POST":
        return redirect("sale_invoice", pk=pk)

    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = _get_session(request, pk)
    if "total_amount" not in session:
        messages.error(request, _("Session expired. Please start from the beginning."))
        return redirect("sale_wizard_step1", pk=pk)

    items = session.get("items", [])
    if not items:
        messages.error(request, _("Add at least one item before submitting."))
        return redirect("sale_invoice", pk=pk)

    try:
        op = _do_submit(request, project, session)
    except Exception as e:
        logger.exception("Error during sale submit")
        messages.error(request, _("Error: %(e)s") % {"e": str(e)})
        return redirect("sale_invoice", pk=pk)

    _clear_session(request, pk)
    messages.success(request, _("Sale recorded successfully."))
    return redirect("operation_detail_view", pk=op.pk)


def _do_submit(request, project, session_data: dict):
    """Delegate to SaleOperation.create_from_session()."""
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        return SaleOperation.create_from_session(
            project=project,
            session_data=session_data,
            officer=request.user,
        )
