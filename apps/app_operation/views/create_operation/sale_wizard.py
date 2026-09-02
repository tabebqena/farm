"""Function-based sale wizard.

A multi-step, session-based flow that builds a sale invoice (project, products
and quantities) in the session and submits it through the sale operation proxy,
creating the dispatch movements and client settlement.
"""

from datetime import date

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from farm.shortcuts import get_object_or_404
from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import Product
from apps.app_inventory.stock import movement_state, portfolio as stock_portfolio
from apps.app_operation.forms import (
    SaleItemForm,
    SaleWizardStep1Form,
    SaleWizardStep2Form,
    SaleWizardStep3Form,
)
from apps.app_operation.models import SaleOperation

from .wizard_base import Wizard

# ---------------------------------------------------------------------------
# Wizard config
# ---------------------------------------------------------------------------

STEPS = {
    1: {"name": _("Basic Info"), "title": _("Sale — Basic Information")},
    2: {"name": _("Total Amount"), "title": _("Sale — Invoice Total")},
    3: {"name": _("Payment"), "title": _("Sale — Payment (optional)")},
}

SALE_WIZARD = Wizard(
    prefix="sale_wizard",
    steps=STEPS,
    counterpart_field="client",
    step1_form_class=SaleWizardStep1Form,
    step2_form_class=SaleWizardStep2Form,
    step3_form_class=SaleWizardStep3Form,
    step1_url="sale_wizard_step1",
    step_new_url="sale_wizard_step_new",
    invoice_url="sale_invoice",
    cancel_url="sale_wizard_cancel",
    submit_url="sale_submit",
    template_name="app_operation/sale_wizard.html",
    invoice_template_name="app_operation/sale_invoice.html",
    recorded_message=_("Sale recorded successfully."),
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
    return project, None


# ---------------------------------------------------------------------------
# Cancel / steps
# ---------------------------------------------------------------------------


def cancel_sale_wizard_view(request, pk):
    return SALE_WIZARD.cancel(request, pk)


def sale_wizard_view(request, pk, step=1):
    project, redir = _load_project(request, pk)
    if redir:
        return redir
    return SALE_WIZARD.handle_wizard(request, pk, step, project)


# ---------------------------------------------------------------------------
# Invoice hub
# ---------------------------------------------------------------------------


def sale_invoice_view(request, pk):
    project, redir = _load_project(request, pk)
    if redir:
        return redir

    def augment_item(item):
        # Augment each item with display fields (product-based)
        product = _get_project_product(project, item.get("product_id"))
        if product is not None:
            template_name = product.product_template.name
            tag = product.unique_id or ""
        else:
            template_name = _("(unknown)")
            tag = ""
        return {"template_name": template_name, "tag": tag}

    return SALE_WIZARD.render_invoice(request, pk, project, augment_item)


# ---------------------------------------------------------------------------
# Select product
# ---------------------------------------------------------------------------


def sale_select_product_view(request, pk):
    """List the seller's EXISTING on-hand products to pick for the sale."""
    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = SALE_WIZARD.get_session(request, pk)
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


def sale_add_item_view(request, pk, idx=None):
    """Add/edit a sale invoice item by selecting an EXISTING product from stock."""
    project, redir = _load_project(request, pk)
    if redir:
        return redir

    session = SALE_WIZARD.get_session(request, pk)
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
            SALE_WIZARD.save_session(request, project.pk, session)
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
    return SALE_WIZARD.delete_item(request, pk, idx)


# ---------------------------------------------------------------------------
# Final submit
# ---------------------------------------------------------------------------


def _do_submit(request, project, session_data):
    """Delegate to SaleOperation.create_from_session()."""
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        return SaleOperation.create_from_session(
            project=project,
            session_data=session_data,
            officer=request.user,
        )


def sale_submit_view(request, pk):
    if request.method != "POST":
        return redirect("sale_invoice", pk=pk)

    project, redir = _load_project(request, pk)
    if redir:
        return redir

    return SALE_WIZARD.submit(request, pk, project, _do_submit)
