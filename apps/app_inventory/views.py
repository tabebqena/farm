import traceback
from datetime import date as today_date

from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.app_entity.models import Entity
from apps.app_inventory.forms import InventoryMovementLineFormSet
from apps.app_inventory.models import InventoryMovement, Product, ProductTemplate
from apps.app_operation.models.operation_type import OperationType


def stock_detail(request, entity_pk):
    from datetime import date

    from apps.app_entity.models import Entity
    from apps.app_inventory.models import (
        InventoryMovementLine,
        InvoiceItem,
        Product,
        ProductLedgerEntry,
    )
    from apps.app_operation.models.operation_type import OperationType

    entity = get_object_or_404(Entity, pk=entity_pk)

    # Get portfolio for this entity as of today
    portfolio = ProductLedgerEntry.portfolio_as_of(entity, date.today())
    product_ids = [item["product_id"] for item in portfolio]

    products = (
        Product.objects.filter(pk__in=product_ids)
        .select_related("product_template")
        .prefetch_related("invoice_items__operation")
        .order_by("product_template__nature", "product_template__name", "pk")
    )

    # Get unreceived purchases (InvoiceItems with no InventoryMovementLines)
    unreceived_purchases = (
        InvoiceItem.objects.filter(operation__operation_type=OperationType.PURCHASE)
        .exclude(pk__in=InventoryMovementLine.objects.values_list("invoice_item_id"))
        .select_related("product", "operation")
        .order_by("-operation__date")
    )

    # Get undelivered sales (InvoiceItems with no InventoryMovementLines)
    undelivered_sales = (
        InvoiceItem.objects.filter(operation__operation_type=OperationType.SALE)
        .exclude(pk__in=InventoryMovementLine.objects.values_list("invoice_item_id"))
        .select_related("product", "operation")
        .order_by("-operation__date")
    )

    return render(
        request,
        "app_inventory/stock_detail.html",
        {
            "entity": entity,
            "products": products,
            "unreceived_items": unreceived_purchases,
            "undelivered_items": undelivered_sales,
        },
    )


def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("product_template").prefetch_related(
            "invoice_items__operation", "ledger_entries"
        ),
        pk=pk,
    )
    return render(request, "app_inventory/product_detail.html", {"product": product})


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

    all_templates = ProductTemplate.objects.all().order_by(
        "nature", "sub_category", "name"
    )
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


def product_template_detail(request, pk):
    template = get_object_or_404(
        ProductTemplate.objects.prefetch_related(
            "entities",
            "product_set__invoice_items__operation",
            "invoices__operation",
        ),
        pk=pk,
    )
    return render(
        request, "app_inventory/product_template_detail.html", {"template": template}
    )


def entity_product_templates_list(request, entity_pk):
    """List product templates assigned to an entity."""
    entity = get_object_or_404(Entity, pk=entity_pk)
    templates = (
        entity.product_templates.all()
        .prefetch_related("entities", "product_set", "invoices")
        .order_by("nature", "sub_category", "name")
    )
    return render(
        request,
        "app_inventory/entity_product_templates_list.html",
        {
            "entity": entity,
            "templates": templates,
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
        sub_category = request.POST.get("sub_category", "").strip()

        try:
            with db_transaction.atomic():
                template = ProductTemplate.objects.create(
                    name=name,
                    nature=nature,
                    default_unit=default_unit,
                    tracking_mode=tracking_mode,
                    sub_category=sub_category,
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


def create_inventory_movement(request, operation_pk):
    """
    Create an InventoryMovement header + lines for a PURCHASE or SALE operation.
    Requires staff user (officer).
    """
    from apps.app_operation.models.operation import Operation

    if not request.user.is_staff:
        messages.error(
            request, _("You must be an officer to create inventory movements.")
        )
        return redirect("entity_list")

    operation = get_object_or_404(Operation, pk=operation_pk)

    if operation.operation_type not in (OperationType.PURCHASE, OperationType.SALE):
        messages.error(
            request,
            _("Inventory movements are only allowed for PURCHASE or SALE operations."),
        )
        return redirect("operation_detail_view", pk=operation_pk)

    if request.method == "POST":
        date_str = request.POST.get("date", "").strip()
        notes = request.POST.get("notes", "").strip()

        try:
            date = parse_date(date_str) if date_str else today_date.today()
            if not date:
                raise ValueError(_("Invalid date format."))

            with db_transaction.atomic():
                movement = InventoryMovement(
                    operation=operation,
                    date=date,
                    officer=request.user,
                    notes=notes,
                )
                movement.full_clean()
                movement.save()

                formset = InventoryMovementLineFormSet(
                    request.POST, instance=movement, operation=operation
                )
                if formset.is_valid():
                    formset.save()
                    messages.success(
                        request,
                        _("Inventory movement created with %(count)s line(s).")
                        % {
                            "count": len(
                                [
                                    f
                                    for f in formset.forms
                                    if f.cleaned_data.get("invoice_item")
                                ]
                            )
                        },
                    )
                    return redirect("operation_detail_view", pk=operation_pk)
                else:
                    messages.error(
                        request,
                        _("Please check the items below for errors."),
                    )
                    raise ValueError(_("Formset validation failed"))
        except Exception as e:
            traceback.print_exc()
            messages.error(request, _("Error: %(error)s") % {"error": str(e)})
            formset = InventoryMovementLineFormSet(request.POST, operation=operation)
            return render(
                request,
                "app_inventory/inventory_movement_form.html",
                {
                    "operation": operation,
                    "formset": formset,
                },
            )

    formset = InventoryMovementLineFormSet(operation=operation)

    return render(
        request,
        "app_inventory/inventory_movement_form.html",
        {
            "operation": operation,
            "formset": formset,
        },
    )
