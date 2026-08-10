import traceback
import uuid
from datetime import date as today_date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.app_base.debug import debug_view
from apps.app_entity.models import Entity
from apps.app_inventory.forms import InventoryMovementLineFormSet
from apps.app_inventory.models import (
    InventoryMovementLine,
    InvoiceItem,
    Product,
    ProductTemplate,
)
from farm.shortcuts import get_object_or_404


def stock_detail(request, entity_pk):
    from datetime import date
    from decimal import Decimal

    from django.db.models import Case, DecimalField, F, Sum, Value, When

    from apps.app_entity.models import Entity
    from apps.app_inventory.models import (
        Product,
        ProductLedgerEntry,
    )
    from apps.app_operation.models.operation_type import OperationType

    entity = get_object_or_404(
        Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
    )

    active_tab = request.GET.get("tab", "live")

    # ------------------------------------------------------------------
    # 1. All products belonging to this entity with movement lines
    # ------------------------------------------------------------------
    base_qs = (
        Product.objects.filter(entity=entity)
        .select_related("product_template")
        .prefetch_related("invoice_items__operation", "movement_lines")
        .order_by("product_template__nature", "product_template__name", "pk")
    )

    # Annotate with net movement quantity (incoming - outgoing)
    incoming_ops = [OperationType.PURCHASE, OperationType.BIRTH]
    outgoing_ops = [OperationType.SALE, OperationType.DEATH, OperationType.CONSUMPTION]

    products_with_qty = base_qs.annotate(
        incoming=Sum(
            Case(
                When(
                    movement_lines__operation__operation_type__in=incoming_ops,
                    movement_lines__reversal_of__isnull=True,
                    then=F("movement_lines__quantity"),
                ),
                default=Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        ),
        outgoing=Sum(
            Case(
                When(
                    movement_lines__operation__operation_type__in=outgoing_ops,
                    movement_lines__reversal_of__isnull=True,
                    then=F("movement_lines__quantity"),
                ),
                default=Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        ),
    )

    # Derive net quantity (incoming - outgoing) for tab filtering.
    # Tab filtering also checks movement line types in Python (below) to
    # determine which exit category a product belongs to.
    products_with_qty = products_with_qty.annotate(
        net_qty=F("incoming") - F("outgoing"),
    )

    # Filter by active tab
    if active_tab == "live":
        products = [
            p for p in products_with_qty if (p.incoming or 0) - (p.outgoing or 0) > 0
        ]
    elif active_tab == "dead":
        products = [
            p
            for p in products_with_qty
            if (p.incoming or 0) - (p.outgoing or 0) <= 0
            and p.movement_lines.filter(
                operation__operation_type=OperationType.DEATH,
                reversal_of__isnull=True,
            ).exists()
        ]
    elif active_tab == "consumed":
        products = [
            p
            for p in products_with_qty
            if (p.incoming or 0) - (p.outgoing or 0) <= 0
            and p.movement_lines.filter(
                operation__operation_type=OperationType.CONSUMPTION,
                reversal_of__isnull=True,
            ).exists()
        ]
    elif active_tab == "sold":
        products = [
            p
            for p in products_with_qty
            if (p.incoming or 0) - (p.outgoing or 0) <= 0
            and p.movement_lines.filter(
                operation__operation_type=OperationType.SALE,
                reversal_of__isnull=True,
            ).exists()
        ]
    else:
        products = list(products_with_qty)

    # ------------------------------------------------------------------
    # 2. Pending items (contracts not yet fully moved) — ledger-based
    # ------------------------------------------------------------------
    pending = ProductLedgerEntry.pending_items(entity=entity, as_of=date.today())
    pending_inbound = [p for p in pending if p["pending_qty"] > 0]
    pending_outbound = [p for p in pending if p["pending_qty"] < 0]

    # ------------------------------------------------------------------
    # 3. Summary calculations — ledger-based (issuance − movement)
    # ------------------------------------------------------------------
    from collections import defaultdict

    portfolio = ProductLedgerEntry.portfolio_as_of(entity, date.today())
    physically_present_qty = sum(item["quantity"] for item in portfolio)

    # Aggregate obligated quantities directly from the ledger.
    # pending_items() returns positive = inbound, negative = outbound.
    obligated_inbound_qty = Decimal("0.00")
    obligated_outbound_qty = Decimal("0.00")
    inbound_by_tmpl_name: dict[str, Decimal] = defaultdict(Decimal)
    outbound_by_tmpl_name: dict[str, Decimal] = defaultdict(Decimal)

    for p in pending:
        name = p["product_template__name"]
        if p["pending_qty"] > 0:
            obligated_inbound_qty += p["pending_qty"]
            inbound_by_tmpl_name[name] += p["pending_qty"]
        else:
            outbound_qty = abs(p["pending_qty"])
            obligated_outbound_qty += outbound_qty
            outbound_by_tmpl_name[name] += outbound_qty

    # ------------------------------------------------------------------
    # 4. Per-template summary cards
    # ------------------------------------------------------------------
    assigned_templates = entity.product_templates.all().order_by("nature", "name")

    # Build product_id → template_id mapping from the base queryset
    product_tmpl_map = {p.pk: p.product_template_id for p in products_with_qty}

    # Group portfolio quantities by template
    physically_present_by_tmpl: dict[int, Decimal] = defaultdict(Decimal)
    for p_item in portfolio:
        tmpl_id = product_tmpl_map.get(p_item["product_id"])
        if tmpl_id:
            physically_present_by_tmpl[tmpl_id] += p_item["quantity"]

    # Build per-template summary list (match by template name for obligations)
    templates_summary = []
    for tmpl in assigned_templates:
        present = physically_present_by_tmpl.get(tmpl.pk, Decimal("0.00"))
        inbound = inbound_by_tmpl_name.get(tmpl.name, Decimal("0.00"))
        outbound = outbound_by_tmpl_name.get(tmpl.name, Decimal("0.00"))
        templates_summary.append(
            {
                "template": tmpl,
                "physically_present_qty": present,
                "obligated_inbound_qty": inbound,
                "obligated_outbound_qty": outbound,
            }
        )

    return render(
        request,
        "app_inventory/stock_detail.html",
        {
            "entity": entity,
            "active_tab": active_tab,
            "products": products,
            "physically_present_qty": physically_present_qty,
            "obligated_inbound_qty": obligated_inbound_qty,
            "obligated_outbound_qty": obligated_outbound_qty,
            "pending_inbound_items": pending_inbound,
            "pending_outbound_items": pending_outbound,
            "templates_summary": templates_summary,
        },
    )


def product_detail(request, pk):
    from decimal import Decimal

    from django.db.models import Sum

    product = get_object_or_404(
        Product.objects.select_related("product_template").prefetch_related(
            "invoice_items__operation",
            "ledger_entries",
            "movement_lines",
        ),
        pk=pk,
        error_message="Product not found or has been deleted.",
    )

    # Compute ledger balance = physically moved quantity/value
    ledger_balance = product.ledger_entries.aggregate(
        total_qty=Sum("quantity_delta"),
        total_value=Sum("value_delta"),
    )
    physically_present_qty = ledger_balance["total_qty"] or Decimal("0.00")
    physically_present_value = ledger_balance["total_value"] or Decimal("0.00")

    context = {
        "product": product,
        "physically_present_qty": physically_present_qty,
        "physically_present_value": physically_present_value,
    }
    return render(request, "app_inventory/product_detail.html", context)


def project_product_templates_setup(request, entity_pk):
    """
    Manage multiple product template assignments for an entity at once.
    Verifies officer permissions and performs a bulk update within a transaction.
    """
    try:
        target_entity = get_object_or_404(
            Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
        )
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
            "invoice_items__operation",
        ),
        pk=pk,
        error_message="Product template not found or has been deleted.",
    )

    context = {"template": template}

    # Handle back button - check if user came from a specific entity
    from_entity_id = request.GET.get("from_entity")
    if from_entity_id:
        from_entity = get_object_or_404(
            Entity,
            pk=from_entity_id,
            error_message="Entity not found or has been deleted.",
        )
        context["from_entity"] = from_entity

    return render(request, "app_inventory/product_template_detail.html", context)


def entity_product_templates_list(request, entity_pk):
    """List product templates assigned to an entity."""
    entity = get_object_or_404(
        Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
    )
    templates = (
        entity.product_templates.all()
        .prefetch_related("entities", "product_set", "invoice_items")
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
        has_tag = request.POST.get("has_tag") == "on"
        sub_category = request.POST.get("sub_category", "").strip()

        try:
            with db_transaction.atomic():
                template = ProductTemplate.objects.create(
                    name=name,
                    nature=nature,
                    default_unit=default_unit,
                    tracking_mode=tracking_mode,
                    sub_category=sub_category,
                    has_tag=has_tag,
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
    Create InventoryMovementLine records for a PURCHASE or SALE operation.
    Requires staff user (officer).
    """
    from apps.app_operation.models.operation import Operation

    if not request.user.is_staff:
        messages.error(
            request, _("You must be an officer to create inventory movements.")
        )
        return redirect("entity_list")

    operation = get_object_or_404(
        Operation,
        pk=operation_pk,
        error_message="Operation not found or has been deleted.",
    )

    if not operation.can_create_movement:
        messages.error(
            request,
            _("Inventory movements are only allowed for PURCHASE or SALE operations."),
        )
        return redirect("operation_detail_view", pk=operation_pk)

    invoice_items_json = InvoiceItem.build_movement_json(operation)

    if request.method == "POST":
        date_str = request.POST.get("date", "").strip()
        notes = request.POST.get("notes", "").strip()

        try:
            date = parse_date(date_str) if date_str else today_date.today()
            if not date:
                raise ValueError(_("Invalid date format."))

            with db_transaction.atomic():
                formset = InventoryMovementLineFormSet(
                    request.POST,
                    queryset=InventoryMovementLine.objects.none(),
                    operation=operation,
                    prefix="lines",
                )
                if formset.is_valid():
                    lines = formset.save(commit=False)
                    for line in lines:
                        line.operation = operation
                        line.date = date
                        line.officer = request.user
                        line.notes = notes
                        # Derive the product from the invoice_item's first linked Product
                        if not line.product_id:
                            first_product = line.invoice_item.products.first()
                            if first_product is None:
                                raise ValidationError(
                                    _("Invoice item %(pk)s has no linked product.")
                                    % {"pk": line.invoice_item.pk}
                                )
                            line.product = first_product
                        line.full_clean()
                        line.save()
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
        except Exception as e:
            traceback.print_exc()
            messages.error(request, _("Error: %(error)s") % {"error": str(e)})
            formset = InventoryMovementLineFormSet(
                request.POST,
                queryset=InventoryMovementLine.objects.none(),
                operation=operation,
                prefix="lines",
            )
            return render(
                request,
                "app_inventory/inventory_movement_form.html",
                {
                    "operation": operation,
                    "formset": formset,
                    "invoice_items_json": invoice_items_json,
                },
            )

    formset = InventoryMovementLineFormSet(
        queryset=InventoryMovementLine.objects.none(),
        operation=operation,
        prefix="lines",
    )

    return render(
        request,
        "app_inventory/inventory_movement_form.html",
        {
            "operation": operation,
            "formset": formset,
            "invoice_items_json": invoice_items_json,
        },
    )


@debug_view
def reverse_inventory_movement_line(request, pk):
    """
    Reverse a single InventoryMovementLine.
    Wraps the model's `reverse()` method in an HTTP request/response cycle.
    """
    if not request.user.is_staff:
        messages.error(request, _("You must be an officer to reverse movement lines."))
        return redirect("entity_list")

    line = get_object_or_404(
        InventoryMovementLine,
        pk=pk,
        error_message="Movement line not found or has been deleted.",
    )

    if InventoryMovementLine.objects.filter(reversal_of=line).exists():
        messages.warning(request, _("This movement line has already been reversed."))
        return redirect("operation_detail_view", pk=line.operation_id)

    if request.method == "POST":
        try:
            with db_transaction.atomic():
                line.reverse(officer=request.user, group_key=uuid.uuid4().hex[:8])
            messages.success(request, _("Movement line reversed successfully."))
            return redirect("operation_detail_view", pk=line.operation_id)
        except Exception as e:
            traceback.print_exc()
            messages.error(
                request,
                _("Error reversing movement line: %(error)s") % {"error": str(e)},
            )

    return render(
        request,
        "app_inventory/reverse_movement_line_confirm.html",
        {"line": line, "operation": line.operation},
    )


@debug_view
def batch_reverse_inventory_movement_lines(request, group_key):
    """
    Reverse all non-reversed InventoryMovementLines sharing a ``group_key``.
    Wraps ``InventoryMovementLine.batch_reverse()`` in an HTTP request/response
    cycle.
    """
    if not request.user.is_staff:
        messages.error(request, _("You must be an officer to reverse movements."))
        return redirect("entity_list")

    lines = InventoryMovementLine.objects.filter(
        group_key=group_key,
        reversal_of__isnull=True,
    ).select_related("operation")

    if not lines.exists():
        messages.error(
            request,
            _("No movement lines found for the given group key."),
        )
        return redirect("operation_list_view")

    # All lines should belong to the same operation — use the first one
    operation = lines[0].operation

    if request.method == "POST":
        try:
            with db_transaction.atomic():
                created = InventoryMovementLine.batch_reverse(
                    lines, officer=request.user
                )
            messages.success(
                request,
                _("%(count)s movement line(s) reversed successfully.")
                % {"count": len(created)},
            )
            return redirect("operation_detail_view", pk=operation.pk)
        except Exception as e:
            traceback.print_exc()
            messages.error(
                request,
                _("Error reversing movement lines: %(error)s") % {"error": str(e)},
            )

    return render(
        request,
        "app_inventory/reverse_movement_confirm.html",
        {"lines": lines, "group_key": group_key, "operation": operation},
    )


@debug_view
def register_deferred_movements(request, operation_pk):
    """
    Register inventory movements for an operation's unmoved products.

    The officer selects an ``InvoiceItem`` and enters a quantity.
    The backend creates ``InventoryMovementLine`` records, branching on
    the product template's tracking mode:
      - INDIVIDUAL → one ``InventoryMovementLine`` per Product (qty=1 each)
      - BATCH/COMMODITY → one ``InventoryMovementLine`` with the full qty

    All created lines share a ``group_key`` so the UI can group them.
    """
    from decimal import Decimal

    from apps.app_operation.models.operation import Operation

    if not request.user.is_staff:
        messages.error(request, _("You must be an officer to create movements."))
        return redirect("entity_list")

    operation = get_object_or_404(
        Operation,
        pk=operation_pk,
        error_message="Operation not found or has been deleted.",
    )
    operation = Operation.objects.cast(operation)

    if not operation.can_create_movement:
        messages.error(
            request, _("Movements are only for PURCHASE or SALE operations.")
        )
        return redirect("operation_detail_view", pk=operation_pk)

    from apps.app_inventory.forms import DeferredMovementForm

    if request.method == "POST":
        form = DeferredMovementForm(request.POST, operation=operation)
        if form.is_valid():
            invoice_item = form.cleaned_data["invoice_item"]
            qty_to_move = form.cleaned_data["quantity"]
            notes = form.cleaned_data.get("notes", "")

            # Determine remaining qty that can be moved
            from django.db.models import Sum

            already_moved = InventoryMovementLine.objects.filter(
                invoice_item=invoice_item,
                reversal_of__isnull=True,
            ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")
            remaining = invoice_item.quantity - already_moved
            if qty_to_move > remaining:
                messages.error(
                    request,
                    _("Cannot move %(qty)s — only %(rem)s remaining for item %(item)s.")
                    % {
                        "qty": qty_to_move,
                        "rem": remaining,
                        "item": invoice_item,
                    },
                )
                return render(
                    request,
                    "app_inventory/deferred_movement_form.html",
                    {"form": form, "operation": operation},
                )

            template = invoice_item.product_template
            group_key = uuid.uuid4().hex[:8]
            products = list(invoice_item.products.all())
            created_count = 0

            try:
                with db_transaction.atomic():
                    if (
                        template.tracking_mode
                        == ProductTemplate.TrackingMode.INDIVIDUAL
                    ):
                        # One line per product
                        for product in products:
                            if created_count >= int(qty_to_move):
                                break
                            if product.deleted_at:
                                continue
                            InventoryMovementLine.objects.create(
                                operation=operation,
                                invoice_item=invoice_item,
                                product=product,
                                quantity=Decimal("1.00"),
                                date=operation.date,
                                officer=request.user,
                                notes=notes,
                                group_key=group_key,
                            )
                            created_count += 1
                    else:
                        # BATCH / COMMODITY: single line with full qty
                        product = products[0] if products else None
                        # If no product exists yet, product=None is fine —
                        # InventoryMovementLine.save() will lazy-create one
                        # for PURCHASE operations.
                        InventoryMovementLine.objects.create(
                            operation=operation,
                            invoice_item=invoice_item,
                            product=product,
                            quantity=qty_to_move,
                            date=operation.date,
                            officer=request.user,
                            notes=notes,
                            group_key=group_key,
                        )
                        created_count = 1

                messages.success(
                    request,
                    _("%(count)d movement line(s) created for item %(item)s.")
                    % {"count": created_count, "item": invoice_item},
                )
                return redirect("operation_detail_view", pk=operation_pk)

            except Exception as e:
                traceback.print_exc()
                messages.error(
                    request,
                    _("Error creating movements: %(error)s") % {"error": str(e)},
                )

        else:
            messages.error(request, _("Please check the form for errors."))

    else:
        form = DeferredMovementForm(operation=operation)

    return render(
        request,
        "app_inventory/deferred_movement_form.html",
        {"form": form, "operation": operation},
    )
