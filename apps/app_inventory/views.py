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
from apps.app_inventory.forms import InventoryMovementLineFormSet, ProductTemplateForm
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

    from django.core.paginator import Paginator
    from django.db.models import Case, DecimalField, F, Q, Sum, Value, When

    from apps.app_entity.models import Entity
    from apps.app_inventory.models import (
        Product,
    )
    from apps.app_inventory.stock import pending_items, portfolio as stock_portfolio
    from apps.app_operation.models.operation_type import OperationType

    entity = get_object_or_404(
        Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
    )

    # ------------------------------------------------------------------
    # 1. All products belonging to this entity with movement lines
    # ------------------------------------------------------------------
    base_qs = (
        Product.objects.filter(entity=entity)
        .select_related("product_template")
        .prefetch_related("invoice_items__operation", "movement_lines")
        .order_by("product_template__nature", "product_template__name", "pk")
    )

    # Search: template name or unique tag
    search_query = request.GET.get("q", "").strip()
    if search_query:
        base_qs = base_qs.filter(
            Q(product_template__name__icontains=search_query)
            | Q(unique_id__icontains=search_query)
        )

    # Direction-aware net movement quantity (incoming − outgoing). A SALE
    # movement is INCOMING for the buyer (product owned by the SALE source, e.g.
    # an internal-client receipt) and OUTGOING for the seller.
    incoming_ops = [OperationType.PURCHASE, OperationType.BIRTH]
    other_outgoing_ops = [OperationType.DEATH, OperationType.CONSUMPTION]
    received_on_sale = Q(
        movement_lines__operation__operation_type=OperationType.SALE,
        movement_lines__operation__source_id=F("entity"),
    )

    active_lines = Q(movement_lines__reversal_of__isnull=True) & Q(
        movement_lines__reversed_by__isnull=True
    )
    incoming_q = active_lines & (
        Q(movement_lines__operation__operation_type__in=incoming_ops)
        | received_on_sale
    )
    outgoing_q = active_lines & (
        Q(movement_lines__operation__operation_type__in=other_outgoing_ops)
        | (
            Q(movement_lines__operation__operation_type=OperationType.SALE)
            & ~received_on_sale
        )
    )

    products_with_qty = base_qs.annotate(
        incoming=Sum(
            Case(
                When(
                    incoming_q,
                    then=F("movement_lines__quantity"),
                ),
                default=Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        ),
        outgoing=Sum(
            Case(
                When(
                    outgoing_q,
                    then=F("movement_lines__quantity"),
                ),
                default=Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        ),
        net_qty=F("incoming") - F("outgoing"),
    )

    # ------------------------------------------------------------------
    # 2. Physically present products (ledger-based, per-product cards)
    # ------------------------------------------------------------------
    # stock.portfolio() returns one row per physically present product with a
    # positive net quantity (computed from the movement lines, no ledger).
    portfolio = stock_portfolio(entity, date.today())
    portfolio_by_product = {row["product_id"]: row for row in portfolio}
    present_product_ids = list(portfolio_by_product.keys())

    if present_product_ids:
        # Physically present = ledger portfolio AND a positive net movement.
        # The net_qty guard is movement-line based (reversal-aware), so a
        # product whose only movement was a now-reversed birth no longer
        # counts as physically present.
        products_qs = products_with_qty.filter(
            pk__in=present_product_ids,
            net_qty__gt=0,
        )
    else:
        products_qs = products_with_qty.none()

    # Build one dict per physically present product for the per-product cards.
    physically_present_products = []
    for p in products_qs:
        row = portfolio_by_product[p.pk]
        physically_present_products.append(
            {
                "product": p,
                "quantity": row["quantity"],
                "value": row["value"],
                "is_animal": p.product_template.nature == ProductTemplate.Nature.ANIMAL,
            }
        )

    # ------------------------------------------------------------------
    # 3. Obligated outbound — aggregate warning only (not per-card metric)
    # ------------------------------------------------------------------
    pending = pending_items(entity=entity, as_of=date.today())
    obligated_outbound_qty = sum(
        abs(p["pending_qty"]) for p in pending if p["pending_qty"] < 0
    )

    # ------------------------------------------------------------------
    # 4. Pagination (live physically present products table)
    # ------------------------------------------------------------------
    paginator = Paginator(products_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "app_inventory/stock_detail.html",
        {
            "entity": entity,
            "physically_present_products": physically_present_products,
            "obligated_outbound_qty": obligated_outbound_qty,
            "products": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "search_query": search_query,
        },
    )


def stock_history(request, entity_pk):
    from datetime import date

    from django.core.paginator import Paginator
    from django.db.models import Q
    from django.utils.dateparse import parse_date

    from apps.app_entity.models import Entity
    from apps.app_inventory.models import InventoryMovementLine
    from apps.app_inventory.stock import pending_items
    from apps.app_operation.models.operation_type import OperationType

    entity = get_object_or_404(
        Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
    )

    inbound_ops = [OperationType.PURCHASE, OperationType.BIRTH]
    outbound_ops = [OperationType.SALE, OperationType.DEATH, OperationType.CONSUMPTION]

    movements = (
        InventoryMovementLine.objects.filter(product__entity=entity)
        .select_related(
            "operation",
            "operation__source",
            "operation__destination",
            "product",
            "product__product_template",
            "invoice_item",
            "officer",
            "reversal_of",
            "reversal_of__operation",
        )
        .order_by("-date", "-created_at")
    )

    # ------------------------------------------------------------------
    # Filters (direction / op-type / search / date range)
    # ------------------------------------------------------------------
    active_direction = request.GET.get("direction", "all")
    active_op_type = request.GET.get("op_type", "")
    search_query = request.GET.get("q", "").strip()
    from_date = request.GET.get("from", "").strip()
    to_date = request.GET.get("to", "").strip()

    if active_direction == "in":
        movements = movements.filter(
            Q(operation__operation_type__in=inbound_ops, reversal_of__isnull=True)
            | Q(reversal_of__operation__operation_type__in=outbound_ops)
        )
    elif active_direction == "out":
        movements = movements.filter(
            Q(operation__operation_type__in=outbound_ops, reversal_of__isnull=True)
            | Q(reversal_of__operation__operation_type__in=inbound_ops)
        )

    if active_op_type:
        movements = movements.filter(operation__operation_type=active_op_type)

    if search_query:
        movements = movements.filter(
            Q(product__unique_id__icontains=search_query)
            | Q(product__product_template__name__icontains=search_query)
        )

    parsed_from = parse_date(from_date) if from_date else None
    if parsed_from:
        movements = movements.filter(date__gte=parsed_from)
    parsed_to = parse_date(to_date) if to_date else None
    if parsed_to:
        movements = movements.filter(date__lte=parsed_to)

    # ------------------------------------------------------------------
    # Summary counts (IN / OUT) over the filtered queryset
    # ------------------------------------------------------------------
    in_q = (
        Q(operation__operation_type__in=inbound_ops, reversal_of__isnull=True)
        | Q(reversal_of__operation__operation_type__in=outbound_ops)
    )
    out_q = (
        Q(operation__operation_type__in=outbound_ops, reversal_of__isnull=True)
        | Q(reversal_of__operation__operation_type__in=inbound_ops)
    )
    inbound_count = movements.filter(in_q).count()
    outbound_count = movements.filter(out_q).count()

    # Attach a per-row direction label for display. A line is IN when it is a
    # forward PURCHASE/BIRTH (or a reversal of an OUT op); otherwise OUT.
    movement_rows = [
        {
            "line": line,
            "direction": (
                "OUT"
                if (
                    line.reversal_of_id is None
                    and line.operation.operation_type in outbound_ops
                )
                or (
                    line.reversal_of_id is not None
                    and line.reversal_of.operation.operation_type in inbound_ops
                )
                else "IN"
            ),
        }
        for line in movements
    ]

    paginator = Paginator(movement_rows, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Pending inbound / outbound obligations (moved from stock detail)
    pending = pending_items(entity=entity, as_of=date.today())
    pending_inbound = [p for p in pending if p["pending_qty"] > 0]
    pending_outbound = [p for p in pending if p["pending_qty"] < 0]

    op_type_choices = [
        (OperationType.PURCHASE.value, OperationType.PURCHASE.label),
        (OperationType.BIRTH.value, OperationType.BIRTH.label),
        (OperationType.SALE.value, OperationType.SALE.label),
        (OperationType.DEATH.value, OperationType.DEATH.label),
        (OperationType.CONSUMPTION.value, OperationType.CONSUMPTION.label),
    ]

    return render(
        request,
        "app_inventory/stock_history.html",
        {
            "entity": entity,
            "movements": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "active_direction": active_direction,
            "active_op_type": active_op_type,
            "search_query": search_query,
            "from_date": from_date,
            "to_date": to_date,
            "op_type_choices": op_type_choices,
            "inbound_count": inbound_count,
            "outbound_count": outbound_count,
            "pending_inbound_items": pending_inbound,
            "pending_outbound_items": pending_outbound,
        },
    )


@debug_view
def quick_consume(request, entity_pk):
    """
    One-step "Consume from stock" — from the stock detail page, pick a
    product and a quantity, and a single POST creates the ConsumptionOperation,
    its invoice item, the auto movement line, and all ledger/transaction
    entries in one step.

    Reuses ``ConsumptionOperation.create(...)`` unchanged — the same proven
    pipeline used by the full consumption form (issuance + payment
    transactions, ``CONSUMPTION_MOVEMENT`` ledger, product ``CONSUMED``).
    Availability / ownership / unit guards are re-checked here for a friendly
    message and again at the model layer (``InventoryMovementLine.clean()``).
    """
    from decimal import Decimal

    from apps.app_entity.models import Entity, EntityType
    from apps.app_inventory.models import Product
    from apps.app_inventory.stock import movement_state
    from apps.app_operation.models.operation_type import OperationType
    from apps.app_operation.models.proxies import ConsumptionOperation

    if not request.user.is_staff:
        messages.error(request, _("You must be an officer to consume from stock."))
        return redirect("stock_detail", entity_pk=entity_pk)

    entity = get_object_or_404(
        Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
    )

    if request.method != "POST":
        return redirect("stock_detail", entity_pk=entity_pk)

    product = get_object_or_404(
        Product.objects.select_related("product_template"),
        pk=request.POST.get("product_id"),
        error_message="Product not found or has been deleted.",
    )

    # Ownership guard: the product must belong to this entity's stock.
    if product.entity_id != entity.id:
        messages.error(request, _("Product does not belong to this stock."))
        return redirect("stock_detail", entity_pk=entity_pk)

    # Nature guard: only FEED / MEDICINE templates accept consumption.
    if not product.product_template.accepts_operation(OperationType.CONSUMPTION):
        messages.error(
            request,
            _("'%(name)s' cannot be consumed.") % {"name": product.product_template.name},
        )
        return redirect("stock_detail", entity_pk=entity_pk)

    try:
        quantity = Decimal(request.POST.get("quantity", ""))
        unit_price = Decimal(request.POST.get("unit_price", ""))
    except Exception:
        messages.error(request, _("Invalid quantity or unit price."))
        return redirect("stock_detail", entity_pk=entity_pk)

    date_str = request.POST.get("date", "").strip()
    date = parse_date(date_str) if date_str else today_date.today()
    if date is None:
        messages.error(request, _("Invalid date format."))
        return redirect("stock_detail", entity_pk=entity_pk)

    description = request.POST.get("description", "").strip()
    if not description:
        description = _("Consumption from stock")

    if quantity <= 0:
        messages.error(request, _("Quantity must be greater than zero."))
        return redirect("stock_detail", entity_pk=entity_pk)

    # Availability guard: cannot consume more than physically on hand.
    available = movement_state(product, as_of=date)["quantity"]
    if quantity > available:
        messages.error(
            request,
            _("Insufficient stock: %(qty)s requested but only %(avail)s available.")
            % {"qty": quantity, "avail": available},
        )
        return redirect("stock_detail", entity_pk=entity_pk)

    # Unit consistency guard: quantity is a multiple of minimum_quantity.
    min_qty = product.product_template.minimum_quantity
    if min_qty and min_qty > 0 and (quantity % min_qty) != 0:
        messages.error(
            request,
            _("Quantity %(qty)s must be a multiple of the minimum increment %(min)s.")
            % {"qty": quantity, "min": min_qty},
        )
        return redirect("stock_detail", entity_pk=entity_pk)

    # System entity — the destination of a consumption write-off.
    system_entity = Entity.objects.filter(entity_type=EntityType.SYSTEM).first()
    if system_entity is None:
        system_entity = Entity.create(EntityType.SYSTEM)

    # Build a single-item formset POST and delegate to the proven factory.
    raw_post = {
        "items-TOTAL_FORMS": "1",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
        "items-0-id": "",
        "items-0-quantity": str(quantity),
        "items-0-unit_price": str(unit_price),
        "items-0-description": description,
        "items-0-selected_product": str(product.pk),
        "items-0-DELETE": "",
    }

    try:
        with db_transaction.atomic():
            op = ConsumptionOperation.create(
                operation_type=OperationType.CONSUMPTION,
                source=entity,
                destination=system_entity,
                amount=(quantity * unit_price).quantize(Decimal("0.01")),
                date=date,
                description=description,
                officer=request.user,
                amount_paid=Decimal("0.00"),
                raw_post=raw_post,
                project=entity,
            )
        messages.success(
            request,
            _("%(label)s recorded successfully.") % {"label": ConsumptionOperation.label},
        )
        return redirect("stock_detail", entity_pk=entity_pk)
    except Exception as e:
        traceback.print_exc()
        messages.error(request, _("Error: %(error)s") % {"error": str(e)})
        return redirect("stock_detail", entity_pk=entity_pk)


def product_detail(request, pk):
    from apps.app_inventory.stock import movement_state

    product = get_object_or_404(
        Product.objects.select_related("product_template").prefetch_related(
            "invoice_items__operation",
            "movement_lines",
        ),
        pk=pk,
        error_message="Product not found or has been deleted.",
    )

    # Physical presence = movement-based stock state (no ledger table).
    state = movement_state(product, as_of=today_date.today())
    physically_present_qty = state["quantity"]
    physically_present_value = state["value"]

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

    form = ProductTemplateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with db_transaction.atomic():
                # Tracking mode is derived from nature — ANIMAL → INDIVIDUAL,
                # everything else → COMMODITY (there is no free choice).
                # ModelForm.clean() runs ProductTemplate.clean() which enforces
                # the animal gating rules (no animal consumed, gives_birth_to ...).
                template = form.save()
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
            "form": form,
            "natures": ProductTemplate.Nature.choices,
            "tracking_modes": ProductTemplate.TrackingMode.choices,
        },
    )


def create_purchase_movement(request, operation_pk):
    """
    Receive (inbound) inventory movements for a PURCHASE operation.

    Split out of the former generic ``create_inventory_movement`` so the
    receive flow is isolated from the SALE dispatch flow. Receiving the
    remaining quantity of a purchased lot is never blocked by the lot's own
    status (see ``InventoryMovementLine.clean()``) — a lot that was partially
    dispatched can still receive the rest of its purchase.
    """
    from apps.app_operation.models.operation_type import OperationType

    return _create_inventory_movement(request, operation_pk, OperationType.PURCHASE)


def create_sale_movement(request, operation_pk):
    """
    Dispatch (outbound) inventory movements for a SALE operation.

    Split out of the former generic ``create_inventory_movement`` so the
    dispatch flow is isolated from the PURCHASE receive flow.
    """
    from apps.app_operation.models.operation_type import OperationType

    return _create_inventory_movement(request, operation_pk, OperationType.SALE)


def create_inventory_movement(request, operation_pk):
    """
    Backwards-compatible dispatcher for the pre-split URL.

    Routes to the type-specific purchase/sale movement view so old links and
    bookmarks keep working.
    """
    from apps.app_operation.models.operation import Operation
    from apps.app_operation.models.operation_type import OperationType

    operation = get_object_or_404(
        Operation,
        pk=operation_pk,
        error_message="Operation not found or has been deleted.",
    )
    operation = Operation.objects.cast(operation)
    if operation.operation_type == OperationType.SALE:
        return redirect("create_sale_movement", operation_pk=operation_pk)
    return redirect("create_purchase_movement", operation_pk=operation_pk)


def _create_inventory_movement(request, operation_pk, expected_type):
    """
    Shared implementation for creating ``InventoryMovementLine`` records for an
    operation of the given ``expected_type`` (PURCHASE or SALE).

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
    # Cast so proxy attributes (e.g. period_entity for the closed-period
    # guard) are resolved from the concrete operation type.
    operation = Operation.objects.cast(operation)

    if operation.operation_type != expected_type:
        messages.error(
            request,
            _("Inventory movements for this operation must use the %(type)s flow.")
            % {"type": expected_type},
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

            # Reject movements dated inside a closed financial period of the
            # operation's governing entity.
            from apps.app_operation.models.period import is_date_in_closed_period

            if is_date_in_closed_period(operation.period_entity, date):
                raise ValidationError(
                    _(
                        "Cannot record a movement dated within a closed financial period."
                    )
                )

            with db_transaction.atomic():
                # Concurrency: lock the operation's products so concurrent
                # movements on the same stock serialize against the
                # availability check (SELECT ... FOR UPDATE; no-op on SQLite).
                Product.lock_ids(
                    Product.objects.filter(
                        invoice_items__operation=operation
                    ).values_list("pk", flat=True)
                )
                formset = InventoryMovementLineFormSet(
                    request.POST,
                    queryset=InventoryMovementLine.objects.none(),
                    operation=operation,
                    prefix="lines",
                )
                if formset.is_valid():
                    from decimal import Decimal

                    from apps.app_operation.models.operation_type import OperationType

                    lines = formset.save(commit=False)
                    created_count = 0
                    for line in lines:
                        line.operation = operation
                        line.date = date
                        line.officer = request.user
                        line.notes = notes

                        template = line.invoice_item.product_template
                        is_individual_purchase = (
                            operation.operation_type == OperationType.PURCHASE
                            and template.tracking_mode
                            == ProductTemplate.TrackingMode.INDIVIDUAL
                        )
                        if is_individual_purchase:
                            # One movement line per animal (qty=1 each). Leaving
                            # product=None lets InventoryMovementLine.save()
                            # lazy-create a new tagged Product per line — the
                            # "one line per purchased animal" contract (same as
                            # create_from_session / register_deferred_movements).
                            # Reusing the item's first linked product would keep
                            # writing every new line against the same animal
                            # instead of materialising a new one.
                            for head_idx in range(max(int(line.quantity), 1)):
                                sub = InventoryMovementLine(
                                    operation=operation,
                                    invoice_item=line.invoice_item,
                                    product=None,  # lazy-created by save()
                                    quantity=Decimal("1.00"),
                                    date=date,
                                    officer=request.user,
                                    notes=notes,
                                    group_key=line.group_key,
                                )
                                sub.full_clean()
                                sub.save()
                                created_count += 1
                            continue

                        # Derive the product from the invoice_item's first linked Product
                        if not line.product_id:
                            first_product = line.invoice_item.products.first()
                            if first_product is None:
                                raise ValidationError(
                                    _("Invoice item %(pk)s has no linked product.")
                                    % {"pk": line.invoice_item.pk}
                                )
                            # Ownership guard (clearer message before model-level
                            # full_clean catches the same case below).
                            owner = operation.inventory_owner_entity
                            if owner is not None and first_product.entity_id != owner.id:
                                raise ValidationError(
                                    _(
                                        "Product '%(p)s' does not belong to '%(entity)s' "
                                        "and cannot be moved out of it."
                                    )
                                    % {"p": first_product, "entity": owner}
                                )
                            line.product = first_product
                        line.full_clean()
                        line.save()
                        created_count += 1
                    messages.success(
                        request,
                        _("Inventory movement created with %(count)s line(s).")
                        % {"count": created_count},
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

            # Determine remaining qty that can be moved (net of reversals —
            # originals that have since been reversed no longer count).
            from django.db.models import Sum

            reversed_originals = InventoryMovementLine.objects.filter(
                invoice_item=invoice_item, reversal_of__isnull=False
            ).values_list("reversal_of_id", flat=True)
            already_moved = (
                InventoryMovementLine.objects.filter(
                    invoice_item=invoice_item,
                    reversal_of__isnull=True,
                )
                .exclude(id__in=list(reversed_originals))
                .aggregate(total=Sum("quantity"))["total"]
                or Decimal("0.00")
            )
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
                    # Concurrency: lock the item's products before the
                    # availability/remaining checks and line inserts.
                    Product.lock_ids(
                        invoice_item.products.values_list("pk", flat=True)
                    )
                    if (
                        template.tracking_mode
                        == ProductTemplate.TrackingMode.INDIVIDUAL
                    ):
                        if products:
                            # One line per existing product
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
                            # No products materialised yet (deferred receipt
                            # of an ordered purchase) — create one line per
                            # head; each line lazy-creates its own tagged
                            # Product (INDIVIDUAL).
                            for head_idx in range(max(int(qty_to_move), 1)):
                                line = InventoryMovementLine(
                                    operation=operation,
                                    invoice_item=invoice_item,
                                    product=None,  # lazy-created by save()
                                    quantity=Decimal("1.00"),
                                    date=operation.date,
                                    officer=request.user,
                                    notes=notes,
                                    group_key=group_key,
                                )
                                line.save()
                                created_count += 1
                    else:
                        # COMMODITY: single line with full qty
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
