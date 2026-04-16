import traceback

from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.app_entity.models import Entity
from apps.app_inventory.models import Invoice, Product, ProductTemplate


def stock_detail(request):
    products = (
        Product.objects.select_related("product_template")
        .prefetch_related("invoice_items__invoice__operation")
        .order_by("product_template__nature", "product_template__name", "pk")
    )
    return render(request, "app_inventory/stock_detail.html", {"products": products})


def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("product_template").prefetch_related(
            "invoice_items__invoice__operation"
        ),
        pk=pk,
    )
    return render(request, "app_inventory/product_detail.html", {"product": product})


def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("operation").prefetch_related("items__product"),
        pk=pk,
    )
    return render(request, "app_inventory/invoice_detail.html", {"invoice": invoice})


def project_product_templates_setup(request, entity_pk):
    """
    Manage multiple product template assignments for an entity at once.
    Verifies officer permissions and performs a bulk update within a transaction.
    """
    try:
        target_entity = get_object_or_404(Entity, pk=entity_pk)
    except Http404 as e:
        messages.error(request, "Target entity not found")
        raise
    if not request.user.is_staff:
        messages.error(request, "The current user is not an officer")

    if request.method == "POST":
        templates_ids = request.POST.getlist("product_templates")
        try:
            with db_transaction.atomic():
                # Sync the Many-to-Many relationship
                target_entity.product_templates.set(templates_ids)
                messages.success(
                    request,
                    _("Products updated successfully for %(ent)s.")
                    % {"ent": target_entity.name},
                )
            return redirect("entity_detail", pk=entity_pk)
        except Exception as e:
            traceback.print_exc()
            messages.error(
                request, _("Transaction Error: %(error)s") % {"error": str(e)}
            )

    all_templates = ProductTemplate.objects.all().order_by("nature", "name")
    enabled_template_ids = target_entity.product_templates.values_list("id", flat=True)

    return render(
        request,
        "app_inventory/product_template_toggle_form.html",
        {
            "entity": target_entity,
            "templates": all_templates,
            "enabled_template_ids": list(enabled_template_ids),
        },
    )


def create_product_template(request):
    """
    Create a new Product Template (Animal, Feed, Medicine, or Product).
    Checks for an 'officer' entity linked to the current user and wraps
    creation in an atomic transaction.
    """
    if not request.user.is_staff:
        raise Http404("Not an officer")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        nature = request.POST.get("nature")
        default_unit = request.POST.get("default_unit", "").strip()
        tracking_mode = request.POST.get("tracking_mode")
        requires_individual_tag = request.POST.get("requires_individual_tag") == "on"

        try:
            with db_transaction.atomic():
                template = ProductTemplate.objects.create(
                    name=name,
                    nature=nature,
                    default_unit=default_unit,
                    tracking_mode=tracking_mode,
                    requires_individual_tag=requires_individual_tag,
                )
                messages.success(
                    request,
                    _("Product template '%(name)s' created successfully.")
                    % {"name": template.name},
                )
                return redirect("entity_list")
        except Exception as e:
            traceback.print_exc()
            messages.error(
                request, _("Transaction Error: %(error)s") % {"error": str(e)}
            )

    return render(
        request,
        "app_inventory/product_template_form.html",
        {
            "natures": ProductTemplate.Nature.choices,
            "tracking_modes": ProductTemplate.TrackingMode.choices,
        },
    )
