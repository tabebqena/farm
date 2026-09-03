"""Views for the inventory app.

Provides the stock detail / history / quick-consume pages, product and
product-template views, and the purchase-receive / sale-dispatch inventory
movement creation, reversal and deferred-movement registration flows.
"""

import uuid
from datetime import date as today_date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views import View

from apps.app_base.logging_utils import logger
from apps.app_entity.models import Entity
from apps.app_inventory.forms import InventoryMovementLineFormSet, ProductTemplateForm
from apps.app_inventory.models import (
    InventoryMovementLine,
    InvoiceItem,
    Product,
    ProductTemplate,
)
from farm.shortcuts import get_object_or_404, paginate


def _stock_portfolio_rows(products_qs, portfolio_by_product):
    """Build the per-product card dicts for the physically present products."""
    rows = []
    for p in products_qs:
        row = portfolio_by_product[p.pk]
        rows.append(
            {
                "product": p,
                "quantity": row["quantity"],
                "value": row["value"],
                "is_animal": p.product_template.nature == ProductTemplate.Nature.ANIMAL,
            }
        )
    return rows


def _build_consume_raw_post(quantity, unit_price, description, product):
    """Build the single-item formset POST dict for ``ConsumptionOperation.create``."""
    return {
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


class StockDetailView(View):
    """Display the physical stock portfolio for an entity."""

    def _base_products_qs(self, entity, search_query):
        """All products belonging to *entity* with movement lines, optionally
        filtered by *search_query*, annotated with the direction-aware net
        movement quantity (incoming − outgoing)."""
        from decimal import Decimal

        from django.db.models import Case, DecimalField, F, Q, Sum, Value, When

        from apps.app_inventory.stock import portfolio_direction_q

        base_qs = (
            Product.objects.filter(entity=entity)
            .select_related("product_template")
            .prefetch_related("invoice_items__operation", "movement_lines")
            .order_by("product_template__nature", "product_template__name", "pk")
        )

        # Search: template name or unique tag
        if search_query:
            base_qs = base_qs.filter(
                Q(product_template__name__icontains=search_query)
                | Q(unique_id__icontains=search_query)
            )

        # Direction-aware net movement quantity (incoming − outgoing). The direction
        # classification lives in stock.portfolio_direction_q() (mirrors
        # stock.movement_delta): SALE is incoming for a buyer receipt, outgoing for
        # a seller dispatch; only active lines count.
        return base_qs.annotate(
            incoming=Sum(
                Case(
                    When(
                        portfolio_direction_q("in"),
                        then=F("movement_lines__quantity"),
                    ),
                    default=Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            ),
            outgoing=Sum(
                Case(
                    When(
                        portfolio_direction_q("out"),
                        then=F("movement_lines__quantity"),
                    ),
                    default=Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            ),
            net_qty=F("incoming") - F("outgoing"),
        )

    def _physically_present_products(self, products_with_qty, entity):
        """Physically present products = ledger portfolio AND a positive net
        movement (reversal-aware). Returns ``(products_qs, card_rows)``."""
        from apps.app_inventory.stock import portfolio as stock_portfolio

        # stock.portfolio() returns one row per physically present product with a
        # positive net quantity (computed from the movement lines, no ledger).
        portfolio = stock_portfolio(entity, today_date.today())
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
        return products_qs, _stock_portfolio_rows(products_qs, portfolio_by_product)

    def _obligated_outbound_qty(self, entity):
        """Obligated outbound — aggregate warning only (not per-card metric)."""
        from apps.app_inventory.stock import pending_items

        pending = pending_items(entity=entity, as_of=today_date.today())
        return sum(
            abs(p["pending_qty"]) for p in pending if p["pending_qty"] < 0
        )

    def get(self, request, *args, **kwargs):
        """Render the physical stock portfolio for an entity."""
        entity_pk = kwargs["entity_pk"]
        entity = get_object_or_404(
            Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
        )

        # 1. All products with movement lines (+ search filter + net-qty annotate)
        search_query = request.GET.get("q", "").strip()
        products_with_qty = self._base_products_qs(entity, search_query)

        # 2. Physically present products (ledger-based, per-product cards)
        products_qs, physically_present_products = self._physically_present_products(
            products_with_qty, entity
        )

        # 3. Obligated outbound — aggregate warning only (not per-card metric)
        obligated_outbound_qty = self._obligated_outbound_qty(entity)

        # 4. Pagination (live physically present products table)
        page_obj, paginator = paginate(request, products_qs)

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


class StockHistoryView(View):
    """Display the movement-line history for an entity's stock."""

    def _history_queryset(self, entity, request):
        """Movement lines for an entity's stock with all filters applied.

        Returns ``(movements, active_direction, active_op_type, search_query,
        from_date, to_date)``.
        """
        from django.db.models import Q

        from apps.app_inventory.stock import history_direction_q

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

        # Filters (direction / op-type / search / date range)
        active_direction = request.GET.get("direction", "all")
        active_op_type = request.GET.get("op_type", "")
        search_query = request.GET.get("q", "").strip()
        from_date = request.GET.get("from", "").strip()
        to_date = request.GET.get("to", "").strip()

        if active_direction == "in":
            movements = movements.filter(history_direction_q("in"))
        elif active_direction == "out":
            movements = movements.filter(history_direction_q("out"))

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

        return (
            movements,
            active_direction,
            active_op_type,
            search_query,
            from_date,
            to_date,
        )

    def _history_rows(self, movements):
        """Attach a per-row direction label for display (reversal-aware, shared
        with stock.line_direction)."""
        from apps.app_inventory.stock import line_direction

        return [
            {"line": line, "direction": line_direction(line)} for line in movements
        ]

    def _history_pending(self, entity):
        """Pending inbound / outbound obligations (moved from stock detail)."""
        from apps.app_inventory.stock import pending_items

        pending = pending_items(entity=entity, as_of=today_date.today())
        pending_inbound = [p for p in pending if p["pending_qty"] > 0]
        pending_outbound = [p for p in pending if p["pending_qty"] < 0]
        return pending_inbound, pending_outbound

    def _history_op_type_choices(self):
        """Operation-type choices for the history filter dropdown."""
        from apps.app_operation.models.operation_type import OperationType

        return [
            (OperationType.PURCHASE.value, OperationType.PURCHASE.label),
            (OperationType.BIRTH.value, OperationType.BIRTH.label),
            (OperationType.SALE.value, OperationType.SALE.label),
            (OperationType.DEATH.value, OperationType.DEATH.label),
            (OperationType.CONSUMPTION.value, OperationType.CONSUMPTION.label),
        ]

    def get(self, request, *args, **kwargs):
        """Render the filtered movement history for an entity's stock."""
        from django.core.paginator import Paginator

        from apps.app_inventory.stock import history_direction_q

        entity_pk = kwargs["entity_pk"]
        entity = get_object_or_404(
            Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
        )

        (
            movements,
            active_direction,
            active_op_type,
            search_query,
            from_date,
            to_date,
        ) = self._history_queryset(entity, request)

        # Summary counts (IN / OUT) over the filtered queryset
        inbound_count = movements.filter(history_direction_q("in")).count()
        outbound_count = movements.filter(history_direction_q("out")).count()

        movement_rows = self._history_rows(movements)
        paginator = Paginator(movement_rows, 25)
        page_obj = paginator.get_page(request.GET.get("page"))

        # Pending inbound / outbound obligations (moved from stock detail)
        pending_inbound, pending_outbound = self._history_pending(entity)

        op_type_choices = self._history_op_type_choices()

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


class QuickConsumeView(View):
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

    def _consume_error_redirect(self, entity_pk, message):
        """Set an error message and redirect back to the stock detail page."""
        messages.error(self.request, message)
        return redirect("stock_detail", entity_pk=entity_pk)

    def _parse_consume_input(self, product, entity_pk):
        """Parse + validate the quick-consume POST fields.

        Returns ``(parsed, None)`` on success (``parsed`` is a
        ``(quantity, unit_price, date, description)`` tuple), or
        ``(None, error_response)`` after setting the error message.
        """
        from decimal import Decimal

        from apps.app_inventory.stock import movement_state

        try:
            quantity = Decimal(self.request.POST.get("quantity", ""))
            unit_price = Decimal(self.request.POST.get("unit_price", ""))
        except Exception:
            return None, self._consume_error_redirect(
                entity_pk, _("Invalid quantity or unit price.")
            )

        date_str = self.request.POST.get("date", "").strip()
        date = parse_date(date_str) if date_str else today_date.today()
        if date is None:
            return None, self._consume_error_redirect(
                entity_pk, _("Invalid date format.")
            )

        description = self.request.POST.get("description", "").strip()
        if not description:
            description = _("Consumption from stock")

        if quantity <= 0:
            return None, self._consume_error_redirect(
                entity_pk, _("Quantity must be greater than zero.")
            )

        # Availability guard: cannot consume more than physically on hand.
        available = movement_state(product, as_of=date)["quantity"]
        if quantity > available:
            return None, self._consume_error_redirect(
                entity_pk,
                _("Insufficient stock: %(qty)s requested but only %(avail)s available.")
                % {"qty": quantity, "avail": available},
            )

        # Unit consistency guard: quantity is a multiple of minimum_quantity.
        min_qty = product.product_template.minimum_quantity
        if min_qty and min_qty > 0 and (quantity % min_qty) != 0:
            return None, self._consume_error_redirect(
                entity_pk,
                _("Quantity %(qty)s must be a multiple of the minimum increment %(min)s.")
                % {"qty": quantity, "min": min_qty},
            )

        return (quantity, unit_price, date, description), None

    def get(self, request, *args, **kwargs):
        """Guard quick-consume GETs and bounce back to the stock detail page."""
        entity_pk = kwargs["entity_pk"]
        if not request.user.is_staff:
            return self._consume_error_redirect(
                entity_pk, _("You must be an officer to consume from stock.")
            )
        return redirect("stock_detail", entity_pk=entity_pk)

    def post(self, request, *args, **kwargs):
        """Create a consumption operation from the one-step stock form."""
        from decimal import Decimal

        from apps.app_entity.models import EntityType
        from apps.app_operation.models.operation_type import OperationType
        from apps.app_operation.models.proxies import ConsumptionOperation

        entity_pk = kwargs["entity_pk"]
        if not request.user.is_staff:
            return self._consume_error_redirect(
                entity_pk, _("You must be an officer to consume from stock.")
            )

        entity = get_object_or_404(
            Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
        )

        product = get_object_or_404(
            Product.objects.select_related("product_template"),
            pk=request.POST.get("product_id"),
            error_message="Product not found or has been deleted.",
        )

        # Ownership guard: the product must belong to this entity's stock.
        if product.entity_id != entity.id:
            return self._consume_error_redirect(
                entity_pk, _("Product does not belong to this stock.")
            )

        # Nature guard: only FEED / MEDICINE templates accept consumption.
        if not product.product_template.accepts_operation(OperationType.CONSUMPTION):
            return self._consume_error_redirect(
                entity_pk,
                _("'%(name)s' cannot be consumed.")
                % {"name": product.product_template.name},
            )

        # Parse + validate quantity / unit price / date / description.
        parsed, error_response = self._parse_consume_input(product, entity_pk)
        if error_response:
            return error_response
        quantity, unit_price, date, description = parsed

        # System entity — the destination of a consumption write-off.
        system_entity = Entity.objects.filter(entity_type=EntityType.SYSTEM).first()
        if system_entity is None:
            system_entity = Entity.create(EntityType.SYSTEM)

        # Build a single-item formset POST and delegate to the proven factory.
        raw_post = _build_consume_raw_post(quantity, unit_price, description, product)

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
            logger.exception("Quick consume from stock failed")
            return self._consume_error_redirect(
                entity_pk, _("Error: %(error)s") % {"error": str(e)}
            )


class ProductDetailView(View):
    """Display a single product's detail (movement-based stock state)."""

    def get(self, request, *args, **kwargs):
        """Render a product's detail page with its physical stock state."""
        from apps.app_inventory.stock import movement_state

        pk = kwargs["pk"]
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


class ProjectProductTemplatesSetupView(View):
    """
    Manage multiple product template assignments for an entity at once.
    Verifies officer permissions and performs a bulk update within a transaction.
    """

    def _setup(self, entity_pk):
        """Load the target entity and check officer permission."""
        try:
            target_entity = get_object_or_404(
                Entity, pk=entity_pk, error_message="Entity not found or has been deleted."
            )
        except Http404 as e:
            messages.error(self.request, "Target entity not found")
            raise
        if not self.request.user.is_staff:
            messages.error(self.request, "The current user is not an officer")
        return target_entity

    def get(self, request, *args, **kwargs):
        """Render the product-template toggle form for an entity."""
        target_entity = self._setup(kwargs["entity_pk"])

        all_templates = ProductTemplate.objects.all().order_by(
            "nature", "sub_category", "name"
        )
        enabled_template_ids = target_entity.product_templates.values_list(
            "id", flat=True
        )

        return render(
            request,
            "app_inventory/product_template_toggle_form.html",
            {
                "entity": target_entity,
                "templates": all_templates,
                "enabled_template_ids": list(enabled_template_ids),
            },
        )

    def post(self, request, *args, **kwargs):
        """Sync the entity's assigned product templates from the submitted ids."""
        entity_pk = kwargs["entity_pk"]
        target_entity = self._setup(entity_pk)

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
            logger.exception("Product template toggle failed")
            messages.error(
                request, _("Transaction Error: %(error)s") % {"error": str(e)}
            )

        all_templates = ProductTemplate.objects.all().order_by(
            "nature", "sub_category", "name"
        )
        enabled_template_ids = target_entity.product_templates.values_list(
            "id", flat=True
        )

        return render(
            request,
            "app_inventory/product_template_toggle_form.html",
            {
                "entity": target_entity,
                "templates": all_templates,
                "enabled_template_ids": list(enabled_template_ids),
            },
        )


class ProductTemplateDetailView(View):
    """Display a single product template's detail."""

    def get(self, request, *args, **kwargs):
        """Render a single product-template detail page."""
        pk = kwargs["pk"]
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


class EntityProductTemplatesListView(View):
    """List product templates assigned to an entity."""

    def get(self, request, *args, **kwargs):
        """Render the list of product templates assigned to an entity."""
        entity_pk = kwargs["entity_pk"]
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


class CreateProductTemplateView(View):
    """
    Create a new Product Template (Animal, Feed, Medicine, or Product).
    Checks for an 'officer' entity linked to the current user and wraps
    creation in an atomic transaction.
    """

    def get(self, request, *args, **kwargs):
        """Render an empty product-template creation form."""
        if not request.user.is_staff:
            raise Http404("Not an officer")

        form = ProductTemplateForm()
        return render(
            request,
            "app_inventory/product_template_form.html",
            {
                "form": form,
                "natures": ProductTemplate.Nature.choices,
                "tracking_modes": ProductTemplate.TrackingMode.choices,
            },
        )

    def post(self, request, *args, **kwargs):
        """Create a product template from a valid form submission."""
        if not request.user.is_staff:
            raise Http404("Not an officer")

        form = ProductTemplateForm(request.POST)
        if form.is_valid():
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
                logger.exception("Product template creation failed")
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


class _InventoryMovementCreateView(View):
    """
    Shared implementation for creating ``InventoryMovementLine`` records for an
    operation of the given ``expected_type`` (PURCHASE or SALE).

    Requires staff user (officer). Concrete subclasses implement
    ``get_expected_type()``.
    """

    def get_expected_type(self):
        """Return the operation type this view creates movements for."""
        raise NotImplementedError()

    def _render_movement_form(self, operation, formset, invoice_items_json):
        """Render the inventory-movement form template with the shared context."""
        return render(
            self.request,
            "app_inventory/inventory_movement_form.html",
            {
                "operation": operation,
                "formset": formset,
                "invoice_items_json": invoice_items_json,
            },
        )

    def _build_formset(self, request, operation, data=None):
        """Construct the movement-line formset (bound to *data* when provided)."""
        return InventoryMovementLineFormSet(
            data,
            queryset=InventoryMovementLine.objects.none(),
            operation=operation,
            prefix="lines",
        )

    def _parse_movement_post(self, request, operation, invoice_items_json):
        """Parse + guard the movement POST date/notes.

        Returns ``(date, notes)`` on success, or a rendered error response (with
        the error message set) when validation fails.
        """
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
            return date, notes
        except Exception as e:
            logger.exception("Movement POST parsing failed")
            messages.error(request, _("Error: %(error)s") % {"error": str(e)})
            formset = self._build_formset(request, operation, data=request.POST)
            return self._render_movement_form(
                operation, formset, invoice_items_json
            )

    def _create_movement_lines_post(
        self, request, operation, date, notes, invoice_items_json
    ):
        """Run the atomic movement-line creation from the POST formset.

        Returns the redirect response on success, a rendered error response on
        exception, or ``None`` when the formset is invalid (the caller falls
        through to re-render the blank form).
        """
        try:
            with db_transaction.atomic():
                # Concurrency: lock the operation's products so concurrent
                # movements on the same stock serialize against the
                # availability check (SELECT ... FOR UPDATE; no-op on SQLite).
                Product.lock_ids(
                    Product.objects.filter(
                        invoice_items__operation=operation
                    ).values_list("pk", flat=True)
                )
                formset = self._build_formset(request, operation, data=request.POST)
                if formset.is_valid():
                    # Movement creation rules (INDIVIDUAL expansion, product
                    # derivation, ownership guard) live on the model so the
                    # purchase/sale flows share one implementation.
                    created_count = InventoryMovementLine.create_for_operation(
                        operation=operation,
                        formset=formset,
                        date=date,
                        officer=request.user,
                        notes=notes,
                    )
                    messages.success(
                        request,
                        _("Inventory movement created with %(count)s line(s).")
                        % {"count": created_count},
                    )
                    return redirect("operation_detail_view", pk=operation.pk)
                else:
                    messages.error(
                        request,
                        _("Please check the items below for errors."),
                    )
                    return None
        except Exception as e:
            logger.exception("Movement line creation failed")
            messages.error(request, _("Error: %(error)s") % {"error": str(e)})
            formset = self._build_formset(request, operation, data=request.POST)
            return self._render_movement_form(
                operation, formset, invoice_items_json
            )
        return None

    def _handle(self, request, *args, **kwargs):
        """Route GET/POST movement creation for the expected operation type."""
        from apps.app_operation.models.operation import Operation

        operation_pk = kwargs["operation_pk"]
        expected_type = self.get_expected_type()

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
            parsed = self._parse_movement_post(request, operation, invoice_items_json)
            if not isinstance(parsed, tuple):
                return parsed
            date, notes = parsed

            response = self._create_movement_lines_post(
                request, operation, date, notes, invoice_items_json
            )
            if response is not None:
                return response

        formset = self._build_formset(request, operation)
        return self._render_movement_form(operation, formset, invoice_items_json)

    def get(self, request, *args, **kwargs):
        """Render the movement form (delegates to ``_handle``)."""
        return self._handle(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Create movements from the submitted formset (delegates to ``_handle``)."""
        return self._handle(request, *args, **kwargs)


class CreatePurchaseMovementView(_InventoryMovementCreateView):
    """
    Receive (inbound) inventory movements for a PURCHASE operation.

    Split out of the former generic ``create_inventory_movement`` so the
    receive flow is isolated from the SALE dispatch flow. Receiving the
    remaining quantity of a purchased lot is never blocked by the lot's own
    status (see ``InventoryMovementLine.clean()``) — a lot that was partially
    dispatched can still receive the rest of its purchase.
    """

    def get_expected_type(self):
        """PURCHASE receive movements."""
        from apps.app_operation.models.operation_type import OperationType

        return OperationType.PURCHASE


class CreateSaleMovementView(_InventoryMovementCreateView):
    """
    Dispatch (outbound) inventory movements for a SALE operation.

    Split out of the former generic ``create_inventory_movement`` so the
    dispatch flow is isolated from the PURCHASE receive flow.
    """

    def get_expected_type(self):
        """SALE dispatch movements."""
        from apps.app_operation.models.operation_type import OperationType

        return OperationType.SALE


class CreateInventoryMovementRedirectView(View):
    """
    Backwards-compatible dispatcher for the pre-split URL.

    Routes to the type-specific purchase/sale movement view so old links and
    bookmarks keep working.
    """

    def dispatch(self, request, *args, **kwargs):
        """Redirect to the type-specific purchase/sale movement view."""
        from apps.app_operation.models.operation import Operation
        from apps.app_operation.models.operation_type import OperationType

        operation_pk = kwargs["operation_pk"]
        operation = get_object_or_404(
            Operation,
            pk=operation_pk,
            error_message="Operation not found or has been deleted.",
        )
        operation = Operation.objects.cast(operation)
        if operation.operation_type == OperationType.SALE:
            return redirect("create_sale_movement", operation_pk=operation_pk)
        return redirect("create_purchase_movement", operation_pk=operation_pk)


class ReverseInventoryMovementLineView(View):
    """
    Reverse a single InventoryMovementLine.
    Wraps the model's `reverse()` method in an HTTP request/response cycle.
    """

    def _ensure_officer(self):
        """Redirect non-officers away with an error message."""
        if not self.request.user.is_staff:
            messages.error(
                self.request, _("You must be an officer to reverse movement lines.")
            )
            return redirect("entity_list")
        return None

    def _load_line(self, pk):
        """Load the movement line by primary key."""
        return get_object_or_404(
            InventoryMovementLine,
            pk=pk,
            error_message="Movement line not found or has been deleted.",
        )

    def _already_reversed(self, line):
        """Return a redirect when the line has already been reversed."""
        if InventoryMovementLine.objects.filter(reversal_of=line).exists():
            messages.warning(
                self.request, _("This movement line has already been reversed.")
            )
            return redirect("operation_detail_view", pk=line.operation_id)
        return None

    def get(self, request, *args, **kwargs):
        """Render the single-line reversal confirmation page."""
        response = self._ensure_officer()
        if response is not None:
            return response
        line = self._load_line(kwargs["pk"])
        response = self._already_reversed(line)
        if response is not None:
            return response
        return render(
            request,
            "app_inventory/reverse_movement_line_confirm.html",
            {"line": line, "operation": line.operation},
        )

    def post(self, request, *args, **kwargs):
        """Reverse the movement line after confirmation."""
        response = self._ensure_officer()
        if response is not None:
            return response
        line = self._load_line(kwargs["pk"])
        response = self._already_reversed(line)
        if response is not None:
            return response
        try:
            with db_transaction.atomic():
                line.reverse(officer=request.user, group_key=uuid.uuid4().hex[:8])
            messages.success(request, _("Movement line reversed successfully."))
            return redirect("operation_detail_view", pk=line.operation_id)
        except Exception as e:
            logger.exception("Movement line reversal failed")
            messages.error(
                request,
                _("Error reversing movement line: %(error)s") % {"error": str(e)},
            )
        return render(
            request,
            "app_inventory/reverse_movement_line_confirm.html",
            {"line": line, "operation": line.operation},
        )


class BatchReverseInventoryMovementLinesView(View):
    """
    Reverse all non-reversed InventoryMovementLines sharing a ``group_key``.
    Wraps ``InventoryMovementLine.batch_reverse()`` in an HTTP request/response
    cycle.
    """

    def _ensure_officer(self):
        """Redirect non-officers away with an error message."""
        if not self.request.user.is_staff:
            messages.error(
                self.request, _("You must be an officer to reverse movements.")
            )
            return redirect("entity_list")
        return None

    def _load_lines(self, group_key):
        """Load the non-reversed lines sharing the group key."""
        lines = InventoryMovementLine.objects.filter(
            group_key=group_key,
            reversal_of__isnull=True,
        ).select_related("operation")

        if not lines.exists():
            messages.error(
                self.request,
                _("No movement lines found for the given group key."),
            )
            return None, redirect("operation_list_view")

        # All lines should belong to the same operation — use the first one
        operation = lines[0].operation
        return lines, None

    def get(self, request, *args, **kwargs):
        """Render the batch-reversal confirmation page."""
        response = self._ensure_officer()
        if response is not None:
            return response
        group_key = kwargs["group_key"]
        lines, response = self._load_lines(group_key)
        if response is not None:
            return response
        assert lines is not None
        return render(
            request,
            "app_inventory/reverse_movement_confirm.html",
            {"lines": lines, "group_key": group_key, "operation": lines[0].operation},
        )

    def post(self, request, *args, **kwargs):
        """Reverse all lines sharing the group key after confirmation."""
        response = self._ensure_officer()
        if response is not None:
            return response
        group_key = kwargs["group_key"]
        lines, response = self._load_lines(group_key)
        if response is not None:
            return response
        assert lines is not None
        operation = lines[0].operation
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
            logger.exception("Batch movement line reversal failed")
            messages.error(
                request,
                _("Error reversing movement lines: %(error)s") % {"error": str(e)},
            )
        return render(
            request,
            "app_inventory/reverse_movement_confirm.html",
            {"lines": lines, "group_key": group_key, "operation": operation},
        )


class RegisterDeferredMovementsView(View):
    """
    Register inventory movements for an operation's unmoved products.

    The officer selects an ``InvoiceItem`` and enters a quantity.
    The backend creates ``InventoryMovementLine`` records, branching on
    the product template's tracking mode:
      - INDIVIDUAL → one ``InventoryMovementLine`` per Product (qty=1 each)
      - BATCH/COMMODITY → one ``InventoryMovementLine`` with the full qty

    All created lines share a ``group_key`` so the UI can group them.
    """

    def _setup(self, operation_pk):
        """Load and validate the operation. Returns ``(operation, response)``."""
        from apps.app_operation.models.operation import Operation

        if not self.request.user.is_staff:
            messages.error(
                self.request, _("You must be an officer to create movements.")
            )
            return None, redirect("entity_list")

        operation = get_object_or_404(
            Operation,
            pk=operation_pk,
            error_message="Operation not found or has been deleted.",
        )
        operation = Operation.objects.cast(operation)

        if not operation.can_create_movement:
            messages.error(
                self.request, _("Movements are only for PURCHASE or SALE operations.")
            )
            return None, redirect("operation_detail_view", pk=operation_pk)

        return operation, None

    def get(self, request, *args, **kwargs):
        """Render the deferred-movement registration form."""
        from apps.app_inventory.forms import DeferredMovementForm

        operation, response = self._setup(kwargs["operation_pk"])
        if response is not None:
            return response
        assert operation is not None
        form = DeferredMovementForm(operation=operation)
        return render(
            request,
            "app_inventory/deferred_movement_form.html",
            {"form": form, "operation": operation},
        )

    def _deferred_form_context(self, form, operation):
        """Shared deferred-movement form context."""
        return {"form": form, "operation": operation}

    def _remaining_moveable_qty(self, invoice_item):
        """Remaining qty that can be moved (net of reversals — originals that
        have since been reversed no longer count)."""
        from decimal import Decimal

        from django.db.models import Sum

        from apps.app_inventory.stock import active_lines_for_item

        already_moved = (
            active_lines_for_item(invoice_item).aggregate(total=Sum("quantity"))[
                "total"
            ]
            or Decimal("0.00")
        )
        return invoice_item.quantity - already_moved

    def _register_deferred_post(self, request, operation, form):
        """Handle a valid deferred-movement POST (remaining-qty guard, atomic
        line creation). Returns the response."""
        from apps.app_inventory.forms import DeferredMovementForm

        invoice_item = form.cleaned_data["invoice_item"]
        qty_to_move = form.cleaned_data["quantity"]
        notes = form.cleaned_data.get("notes", "")

        # Determine remaining qty that can be moved (net of reversals —
        # originals that have since been reversed no longer count).
        remaining = self._remaining_moveable_qty(invoice_item)
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
                self._deferred_form_context(form, operation),
            )

        group_key = uuid.uuid4().hex[:8]

        try:
            with db_transaction.atomic():
                # Concurrency: lock the item's products before the
                # availability/remaining checks and line inserts.
                Product.lock_ids(
                    invoice_item.products.values_list("pk", flat=True)
                )
                created_count = invoice_item.create_movements(
                    operation=operation,
                    qty_to_move=qty_to_move,
                    date=operation.date,
                    officer=request.user,
                    notes=notes,
                    group_key=group_key,
                )

            messages.success(
                request,
                _("%(count)d movement line(s) created for item %(item)s.")
                % {"count": created_count, "item": invoice_item},
            )
            return redirect("operation_detail_view", pk=operation.pk)

        except Exception as e:
            logger.exception("Deferred movement registration failed")
            messages.error(
                request,
                _("Error creating movements: %(error)s") % {"error": str(e)},
            )

        return render(
            request,
            "app_inventory/deferred_movement_form.html",
            self._deferred_form_context(form, operation),
        )

    def post(self, request, *args, **kwargs):
        """Register deferred movement lines for the selected invoice item."""
        from apps.app_inventory.forms import DeferredMovementForm

        operation, response = self._setup(kwargs["operation_pk"])
        if response is not None:
            return response
        assert operation is not None

        form = DeferredMovementForm(request.POST, operation=operation)
        if form.is_valid():
            return self._register_deferred_post(request, operation, form)

        messages.error(request, _("Please check the form for errors."))
        return render(
            request,
            "app_inventory/deferred_movement_form.html",
            self._deferred_form_context(form, operation),
        )
