
"""Core operation model and its mixins.

Defines the shared :class:`Operation` base record (officer, dates, period,
amounts and related-transaction behaviour) that every concrete operation proxy
subclasses, together with :class:`InventoryOperationMixin` for stock-bearing
operations and the transaction / stock-event mixins used by the proxies.
"""

from datetime import date as today_date
from decimal import Decimal
from typing import List

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.app_base.logging_utils import audit_logger, logger
from apps.app_base.mixins import (
    AdjustableMixin,
    AmountCleanMixin,
    ImmutableMixin,
    LinkedIssuanceTransactionMixin,
    LinkedPaymentTransactionMixin,
    LinkedRePaymentTransactionMixin,
    OfficerMixin,
)
from apps.app_base.models import BaseModel, ReversableModel
from apps.app_transaction.transaction_type import TransactionType

from .managers import AllOperationManager, OperationManager
from .operation_type import OperationType

# TODO use database level constrains for data integrity.
# TODO: "Financial Statement" method
# TODO: Integrity check method


class InventoryOperationMixin:
    """Inventory-touching behavior shared by every ``Operation``.

    Owns the inventory ownership mapping (``inventory_owner_entity`` /
    ``inventory_receiving_entity``), manual-movement eligibility
    (``can_create_movement``), invoice-item movement summaries
    (``get_items_data``), auto movement creation for the stock events
    (``save_inventory`` → ``_auto_create_inventory_movements``) and the
    reversal inventory hooks. Non-inventory operations get neutral defaults
    (None / False / empty), so inheriting this is safe for every proxy.
    """

    # ------------------------------------------------------------------
    # Inventory ownership helpers
    # ------------------------------------------------------------------

    @property
    def inventory_owner_entity(self):
        """
        The entity whose physical inventory is consumed by this operation's
        movements — used to filter and validate stock selection.

        Returns None for inbound (PURCHASE/BIRTH) and non-inventory operations.
        """
        from .operation_type import OperationType

        if self.operation_type == OperationType.SALE:
            # The selling project is the destination (source is the client).
            return self.destination
        if self.operation_type in (
            OperationType.DEATH,
            OperationType.CONSUMPTION,
            OperationType.CAPITAL_LOSS,
        ):
            # The project whose assets are written off is the source.
            return self.source
        if self.operation_type == OperationType.CAPITAL_GAIN:
            # The project whose assets gain value is the destination.
            return self.destination
        return None

    @property
    def inventory_receiving_entity(self):
        """
        The entity whose physical inventory receives the products created by
        this operation's inbound movements (PURCHASE / BIRTH).

        PURCHASE: the project is the source; BIRTH: the project is the
        destination (the source is the System entity). Returns None for
        non-inbound operations.
        """
        from .operation_type import OperationType

        if self.operation_type == OperationType.BIRTH:
            return self.destination
        if self.operation_type == OperationType.PURCHASE:
            return self.source
        return None

    @property
    def can_create_movement(self) -> bool:
        """Whether this operation supports manual inventory movements."""
        from .operation_type import OperationType

        return self.operation_type in (OperationType.PURCHASE, OperationType.SALE)

    # ------------------------------------------------------------------
    # Inventory / invoice helpers
    # ------------------------------------------------------------------

    def get_items_data(self):
        """
        Build a list of dicts with movement summaries for each invoice item.
        Used by the detail view to display received/delivered quantities.

        Each entry contains:
        - item: the InvoiceItem instance
        - moved_qty: total quantity moved (non-reversal lines)
        - remaining_qty: quantity still to be moved
        - is_fully_moved: True when remaining_qty <= 0
        - is_inbound: True for PURCHASE (receiving), False for SALE (delivering)
        - movement_lines: queryset of active (non-reversal) movement lines
        - grouped_lines: all movement lines grouped by group_key, with net totals
        """
        from decimal import Decimal

        from django.db.models import Sum

        from apps.app_inventory.models import InventoryMovementLine
        from apps.app_inventory.stock import active_lines_for_item

        from .operation_type import OperationType

        items = getattr(self, "_cached_items", None)
        if items is None:
            items = self.items.all()

        items_data = []
        is_inbound = self.operation_type == OperationType.PURCHASE

        for item in items:
            # Aggregate total moved quantity (only active, non-reversal lines —
            # originals that have since been reversed no longer count).
            active_lines = active_lines_for_item(item)
            agg = active_lines.aggregate(total=Sum("quantity"))
            moved_qty = agg["total"] or Decimal("0.00")
            remaining_qty = item.adjusted_quantity - moved_qty

            # Active movement lines (non-reversal, not reversed) for quick reference
            movement_lines = active_lines.select_related("product")

            # All movement lines including reversals, grouped by group_key
            all_lines = InventoryMovementLine.objects.filter(
                invoice_item=item,
            ).select_related("product")

            # Group by group_key (blank/empty group_key → "Individual")
            groups = {}
            for ml in all_lines:
                key = ml.group_key or ""
                if key not in groups:
                    groups[key] = {"group_key": ml.group_key, "lines": []}
                groups[key]["lines"].append(ml)

            # Compute net totals per group
            grouped_lines = []
            for key, group in groups.items():
                net_qty = Decimal("0.00")
                for ml in group["lines"]:
                    if ml.reversal_of_id:
                        net_qty -= ml.quantity
                    else:
                        net_qty += ml.quantity
                group["total_net_qty"] = net_qty
                grouped_lines.append(group)

            # Sort groups: non-empty group_keys first, then by net_qty desc
            grouped_lines.sort(
                key=lambda g: (0 if g["group_key"] else 1, -g["total_net_qty"])
            )

            items_data.append(
                {
                    "item": item,
                    "moved_qty": moved_qty,
                    "remaining_qty": remaining_qty,
                    "is_fully_moved": remaining_qty <= Decimal("0.00"),
                    "is_inbound": is_inbound,
                    "movement_lines": movement_lines,
                    "grouped_lines": grouped_lines,
                }
            )
        return items_data

    def save_inventory(self, bound_formset):
        """
        Called inside an atomic block after the formset is saved.

        Creates the physical InventoryMovementLine records that stock queries
        are built from (there is no separate ledger table anymore):

        * BIRTH/DEATH/CONSUMPTION → auto-creates movement lines
        * DEATH/CONSUMPTION → links the selected products to their items
        * CAPITAL_GAIN/LOSS → NOT handled here — value-only; the capital proxy
          records the product's signed valuation via ``add_valuation()``
          (creates a ``ProductCapitalValuation`` row, never an InvoiceItem or
          a movement line)
        * PURCHASE/SALE    → no movement here (movement lines are
          user-driven or created by the sale wizard later)

        Products are created lazily at movement time, not at contract time.
        """
        from django.utils.translation import gettext as _

        if self.operation_type in (
            OperationType.BIRTH,
            OperationType.DEATH,
            OperationType.CONSUMPTION,
        ):
            self._auto_create_inventory_movements(bound_formset)

        if self.operation_type in (
            OperationType.DEATH,
            OperationType.CONSUMPTION,
        ):
            # Build product_map: {invoice_item_pk: product} for operations
            # where products are known at creation time
            for form in bound_formset.forms:
                item = form.instance
                if not item.pk:
                    continue
                selected = form.cleaned_data.get("selected_product")
                if selected:
                    is_reversal = getattr(self, "reversal_of_id", None) is not None
                    # A DEATH/CONSUMPTION auto-movement already made the selected
                    # product terminal (movement-based status) before this point,
                    # so allow the matching terminal status during validation
                    # (via the same allow_adjustment hook the movement clean uses).
                    allow_terminal = self.operation_type in (
                        OperationType.DEATH,
                        OperationType.CONSUMPTION,
                    )
                    selected.validate_active(
                        allow_reversal=is_reversal, allow_adjustment=allow_terminal
                    )
                    # Ownership guard: the selected product must belong to the
                    # entity whose inventory this operation consumes.
                    owner = self.inventory_owner_entity
                    if not is_reversal and owner is not None:
                        if selected.entity_id != owner.id:
                            raise ValidationError(
                                _(
                                    "Product '%(p)s' does not belong to '%(entity)s' "
                                    "and cannot be used in this operation."
                                )
                                % {"p": selected, "entity": owner}
                            )
                    selected.invoice_items.add(item)

    def _auto_create_inventory_movements(self, bound_formset):
        """
        Auto-create InventoryMovementLine records for BIRTH, DEATH and
        CONSUMPTION operations.

        BIRTH:       System entity → Project entity  (product created lazily)
        DEATH:       Project entity → System entity  (product must already exist)
        CONSUMPTION: Project entity → System entity  (product must already exist)

        Every line is validated (``full_clean``) before save so the ownership
        and availability guards also apply to these auto-created movements.
        """
        import uuid

        group_key = uuid.uuid4().hex[:8]
        self._lock_selected_products(bound_formset)

        for form in bound_formset.forms:
            item = form.instance
            if not item.pk:
                continue

            if self.operation_type == OperationType.BIRTH:
                lines = self._build_birth_lines(item, form, group_key)
            elif self.operation_type in (
                OperationType.DEATH,
                OperationType.CONSUMPTION,
            ):
                line = self._build_terminal_line(item, form, group_key)
                if line is None:
                    continue
                lines = [line]
            else:
                continue

            for line in lines:
                line.full_clean()
                line.save()

    def _lock_selected_products(self, bound_formset):
        """Concurrency: lock the selected products for the duration of this
        transaction so concurrent DEATH/CONSUMPTION on the same stock cannot
        both pass the availability check (SELECT ... FOR UPDATE; no-op on
        SQLite)."""
        if self.operation_type in (OperationType.DEATH, OperationType.CONSUMPTION):
            from apps.app_inventory.models import Product

            selected_ids = [
                form.cleaned_data.get("selected_product").pk
                for form in bound_formset.forms
                if form.instance.pk and form.cleaned_data.get("selected_product")
            ]
            Product.lock_ids(selected_ids)

    def _build_birth_lines(self, item, form, group_key):
        """Build the BIRTH movement lines for one invoice item.

        INDIVIDUAL → one qty-1 line per head, each lazy-creating its own tagged
        Product (with the birth-specific attributes forwarded via transient
        attributes, mirroring ``_lazy_unique_id``). COMMODITY → a single line
        (``product=None`` → created lazily by ``save()``)."""
        from decimal import Decimal

        from apps.app_inventory.models import InventoryMovementLine, ProductTemplate

        if (
            item.product_template.tracking_mode
            == ProductTemplate.TrackingMode.INDIVIDUAL
        ):
            birth_attrs = {}
            if getattr(form, "is_birth", False):
                birth_attrs = {
                    "_lazy_gender": form.cleaned_data.get("gender") or None,
                    "_lazy_birth_date": form.cleaned_data.get("birth_date")
                    or self.date,
                    "_lazy_mother": form.cleaned_data.get("mother") or None,
                }
            # One line per head — each lazy-creates its own tagged Product
            # (e.g. 5 calves → 5 movement lines, 5 products).
            lines = []
            for head_idx in range(int(item.quantity)):
                line = InventoryMovementLine(
                    operation=self,
                    invoice_item=item,
                    quantity=Decimal("1"),
                    date=self.date,
                    officer=self.officer,
                    group_key=group_key,
                )
                for attr, value in birth_attrs.items():
                    setattr(line, attr, value)
                lines.append(line)
            return lines
        # COMMODITY: product=None → created lazily by save()
        return [
            InventoryMovementLine(
                operation=self,
                invoice_item=item,
                quantity=item.quantity,
                date=self.date,
                officer=self.officer,
                group_key=group_key,
            )
        ]

    def _build_terminal_line(self, item, form, group_key):
        """Build the DEATH/CONSUMPTION movement line for one invoice item, or
        ``None`` when no product was selected."""
        from apps.app_inventory.models import InventoryMovementLine

        selected = form.cleaned_data.get("selected_product")
        if not selected:
            return None
        return InventoryMovementLine(
            operation=self,
            invoice_item=item,
            quantity=item.quantity,
            date=self.date,
            officer=self.officer,
            group_key=group_key,
            product=selected,
        )

    # ------------------------------------------------------------------
    # Reversal inventory hooks
    # ------------------------------------------------------------------

    def _validate_reversal_inventory_guards(self):
        """Reversal dependency guard (called before ``super().reverse()``).

        Do not reverse an operation whose products were moved again in a later
        non-reversed operation. For the outbound ops (DEATH/CONSUMPTION/SALE)
        the reversal would resurrect stock that has since been consumed/sold/
        written off. For BIRTH (an inbound op) the reversal would push a
        newborn's net presence negative once its born value was dispatched by
        a later SALE/DEATH/CONSUMPTION, so the guard is extended to BIRTH too
        (docs/specs/operations/op_17_birth.md §5.2.1 VR4).

        Pinned by the reachable scenarios:
          - Sale:  test_reversal_blocked_when_product_moved_again_in_later_sale
          - Consumption: test_reversal_blocked_when_product_moved_again_in_later_consumption
          - Birth: test_reversal_blocked_when_born_product_moved_again_in_later_death
        Death cannot reach this branch via normal flows (no partial death — a
        fully written-off product is terminal), so the DEATH case is defensive
        (see docs/specs/operations/op_18_death.md §5.2.1 VR4).
        """
        from django.utils.translation import gettext as _

        if type(self).has_invoice and self.operation_type in (
            OperationType.BIRTH,
            OperationType.DEATH,
            OperationType.CONSUMPTION,
            OperationType.SALE,
        ):
            from apps.app_inventory.models import InventoryMovementLine

            product_ids = list(
                self.movement_lines.filter(reversal_of__isnull=True).values_list(
                    "product_id", flat=True
                )
            )
            if product_ids:
                downstream = (
                    InventoryMovementLine.objects.filter(
                        product_id__in=product_ids,
                        reversal_of__isnull=True,
                    )
                    .exclude(operation=self)
                    .filter(
                        operation__operation_type__in=[
                            OperationType.SALE,
                            OperationType.DEATH,
                            OperationType.CONSUMPTION,
                        ]
                    )
                )
                if downstream.exists():
                    raise ValidationError(
                        _(
                            "Cannot reverse this operation: its products were "
                            "moved again in a later operation."
                        )
                    )

    def _reverse_inventory_movements(self, officer, date):
        """Reverse the operation's inventory movements (called after reversal).

        * PURCHASE / SALE — user-driven movements must be reversed by the user
          first. Only *active* movement lines block reversal: an original that
          has already been reversed (its mirror exists) and a reversal (mirror)
          line itself are excluded, so reversing all movements unlocks the
          operation reversal.
        * BIRTH / DEATH / CONSUMPTION — auto-created movements are tightly
          coupled to the operation, so each active line is reversed
          automatically.
        """
        from django.utils.translation import gettext as _

        if self.operation_type in (OperationType.PURCHASE, OperationType.SALE):
            moved = self.movement_lines.filter(
                reversal_of__isnull=True,
                reversed_by__isnull=True,
            ).exists()
            if moved:
                raise ValidationError(
                    _(
                        "Cannot reverse this operation. "
                        "Reverse all inventory movements first."
                    )
                )
        elif self.operation_type in (
            OperationType.BIRTH,
            OperationType.DEATH,
            OperationType.CONSUMPTION,
        ):
            for line in self.movement_lines.filter(reversal_of__isnull=True):
                line.reverse(officer=officer, date=date)


class Operation(
    ImmutableMixin,
    AmountCleanMixin,
    OfficerMixin,
    InventoryOperationMixin,
    ReversableModel,
    BaseModel,
):
    """
    Central financial operation record.
    All type-specific logic lives in proxy subclasses.
    This class holds only shared fields and shared behavior.
    """

    _immutable_fields = {"source": {}, "destination": {}, "amount": {}, "period": {}}
    _amount_name = "amount"
    _adjustments_related_name = "adjustments"

    source = models.ForeignKey(
        to="app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="operations_outgoing",
    )
    destination = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="operations_incoming",
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    operation_type = models.CharField(max_length=30, choices=OperationType.choices)
    date = models.DateField(default=today_date.today)
    description = models.TextField(blank=True)
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="operations_supervised",
    )
    period = models.ForeignKey(
        "app_operation.FinancialPeriod",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operations",
    )
    category = models.ForeignKey(
        "app_entity.FinancialCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operations",
    )

    objects = OperationManager()
    all_objects = AllOperationManager()

    # Config defaults — overridden as class attrs on each proxy model
    url_str: str | None = None
    label: str | None = None
    _source_role: str | None = None
    _dest_role: str | None = None
    can_pay: bool = False
    is_partially_payable: bool = False
    _is_one_shot_operation: bool = False
    has_category: bool = False
    has_repayment: bool = False
    repayment_label: str | None = None
    has_invoice: bool = False
    has_capital_valuation: bool = False
    theme_color: str = "danger"
    theme_icon: str = "bi-box-arrow-up-right"
    creates_assets = False
    is_adjustable = False

    # ------------------------------------------------------------------
    # Eligibility helpers
    # ------------------------------------------------------------------

    @property
    def is_items_adjustable(self) -> bool:
        """Whether invoice-item adjustments are allowed on this operation.

        Derived from ``has_invoice`` — only operations that carry invoice
        items (PURCHASE / SALE) can have their line items adjusted.
        """
        return type(self).has_invoice

    @property
    def can_repay(self) -> bool:
        """Whether this operation supports repayments (e.g. loans, worker advances)."""
        return type(self).has_repayment

    @property
    def is_one_shot(self) -> bool:
        """Whether this operation settles in full at creation (one-shot).

        Public, readable alias of the ``_is_one_shot_operation`` config flag that
        proxies use. One-shot operations (cash flows, funding, corrections,
        internal transfers, worker advances) write their issuance + single payment
        pair atomically at creation (see ``OneShotTransactionMixin``).
        """
        return self._is_one_shot_operation

    class Meta:
        verbose_name = "Operation"
        verbose_name_plural = "Operations"
        ordering = ["-date", "-created_at"]

    # ------------------------------------------------------------------
    # Request resolution
    # ------------------------------------------------------------------

    @classmethod
    def _type_config(cls, operation_type=None) -> dict:
        """
        Per-type config overrides used by ``resolve_request`` for proxy classes
        that serve multiple operation types (e.g. CorrectionOperation). The base
        implementation returns ``{}`` — single-type proxies read their class attrs
        directly.
        """
        return {}

    @classmethod
    def resolve_request(cls, url_pk, request, operation_type=None) -> dict:
        """
        Resolves a request into a unified config + entity dict.
        Call on the proxy class: e.g. PurchaseOperation.resolve_request(pk, request)
        """
        from apps.app_entity.models import Entity, EntityType
        from farm.shortcuts import get_object_or_404

        cfg = cls._type_config(operation_type)
        url_entity = get_object_or_404(
            Entity, pk=url_pk, error_message="Entity not found or has been deleted."
        )
        source_role = cfg.get("_source_role", cls._source_role)
        dest_role = cfg.get("_dest_role", cls._dest_role)

        world_entity = None
        if source_role == "world" or dest_role == "world":
            world_entity = Entity.objects.filter(entity_type=EntityType.WORLD).first()
        system_entity = None
        if source_role == "system" or dest_role == "system":
            system_entity = Entity.objects.filter(entity_type=EntityType.SYSTEM).first()

        secondary_pk = request.POST.get("secondary_entity")
        secondary_entity = (
            get_object_or_404(
                Entity,
                pk=secondary_pk,
                error_message="Secondary entity not found or has been deleted.",
            )
            if secondary_pk
            else None
        )

        def resolve(role):
            if role == "world":
                return world_entity
            if role == "system":
                return system_entity
            if role == "url":
                return url_entity
            if role == "post":
                return secondary_entity
            return None

        return {
            "proxy_cls": cls,
            "label": cfg.get("label", cls.label),
            "url_str": cfg.get("url_str", cls.url_str),
            "source": source_role,
            "dest": dest_role,
            "can_pay": cls.can_pay,
            "is_partially_payable": cls.is_partially_payable,
            "has_category": cls.has_category,
            "has_repayment": cls.has_repayment,
            "has_invoice": cls.has_invoice,
            "has_capital_valuation": cls.has_capital_valuation,
            "repayment_transaction_type": getattr(
                cls, "_repayment_transaction_type", None
            ),
            "theme_color": cfg.get("theme_color", cls.theme_color),
            "theme_icon": cfg.get("theme_icon", cls.theme_icon),
            "url_entity": url_entity,
            "secondary_entity": secondary_entity,
            "source_entity": resolve(source_role),
            "dest_entity": resolve(dest_role),
        }

    # ------------------------------------------------------------------
    # Factory — create an operation with all side-effects
    # ------------------------------------------------------------------

    # ── Shared helpers for proxy subclasses ─────────────────────────────

    @classmethod
    def _validate_item_totals(
        cls, items_data: list[dict], declared_total: Decimal
    ) -> None:
        """
        Validate that the sum of (item quantity × item unit_price)
        matches the declared total.

        Used by proxy subclasses (Purchase, Sale) that create invoice
        items from structured data rather than form submissions.

        Raises ``ValueError`` on mismatch.
        """
        from django.utils.translation import gettext as _

        computed = sum(
            Decimal(item["quantity"]) * Decimal(item["unit_price"])
            for item in items_data
        )
        if abs(computed - declared_total) > Decimal("0.01"):
            raise ValueError(
                _("Items total %(items)s does not match declared total %(total)s.")
                % {"items": computed, "total": declared_total}
            )

    @classmethod
    def _build_invoice_items(cls, operation, items_data: list[dict]) -> list:
        """
        Create ``InvoiceItem`` records from a list of item dicts.

        Each dict requires:
        - ``product_template_id`` (int/str)
        - ``quantity`` (str or Decimal)
        - ``unit_price`` (str or Decimal)

        Each dict may include:
        - ``description`` (str)

        Returns the list of created ``InvoiceItem`` instances.

        Raises ``ValidationError`` if a referenced product template does
        not exist.
        """
        from django.utils.translation import gettext as _

        from apps.app_inventory.models import InvoiceItem, ProductTemplate

        invoice_items = []
        for item_data in items_data:
            try:
                template = ProductTemplate.objects.get(
                    pk=item_data["product_template_id"]
                )
            except ProductTemplate.DoesNotExist:
                raise ValidationError(
                    _("Product template not found or has been deleted.")
                )

            invoice_item = InvoiceItem.objects.create(
                operation=operation,
                product_template=template,
                description=item_data.get("description", ""),
                quantity=Decimal(item_data["quantity"]),
                unit_price=Decimal(item_data["unit_price"]),
            )
            invoice_items.append(invoice_item)

        return invoice_items

    @classmethod
    def _resolve_counterparty(cls, session_data, key, label):
        """
        Look up the operation's counterparty entity from wizard session data.

        Used by proxy ``create_from_session`` factories (Sale → client,
        Purchase → vendor). Raises a translated ``ValidationError`` when the
        selected counterparty has been deleted since the wizard opened.
        """
        from django.utils.translation import gettext as _

        from apps.app_entity.models import Entity

        try:
            return Entity.objects.get(pk=session_data[key])
        except Entity.DoesNotExist:
            raise ValidationError(
                _("%(label)s not found or has been deleted.") % {"label": label}
            )

    @classmethod
    def create(
        cls,
        *,
        operation_type: str,
        source,
        destination,
        amount: "Decimal",
        date,
        description: str,
        officer,
        amount_paid: "Decimal | None" = None,
        raw_post=None,
        project=None,
        **kwargs,
    ) -> "Operation":
        """
        Create a fully-formed operation inside a single atomic transaction.

        Orchestrates the full creation pipeline:

          1. Construct and ``save()`` the operation instance
             (triggers ``full_clean()`` → ``clean_fields()`` → ``clean()``
              → ``super().save()`` → ``post_save_tasks``)
          2. Process payment  (if ``cls.can_pay`` and ``amount_paid > 0``)
          3. Process invoice  (if ``cls.has_invoice`` and ``raw_post`` provided)

        Proxy subclasses may **override** this method to inject type-specific
        logic before/after calling ``super().create()``.

        Returns the saved ``Operation`` instance (cast to the proxy class
        when accessed via the proxy).

        Raises ``ValidationError`` (or ``ValueError``) on failure — the
        caller is responsible for catching and presenting the error.
        """
        from django.db import transaction

        with transaction.atomic():
            # ── 1. Construct & save ──────────────────────────────────────
            op = cls(
                operation_type=operation_type,
                source=source,
                destination=destination,
                amount=amount,
                date=date,
                description=description,
                officer=officer,
                **kwargs,
            )
            op.save()  # full_clean → clean_fields → clean → save → post_save_tasks

            # ── 2. Payment processing ────────────────────────────────────
            cls._process_creation_payment(op, amount_paid, officer, date)

            # ── 3. Invoice / inventory processing ────────────────────────
            cls._process_creation_invoice(op, operation_type, raw_post, project)

        return op

    @classmethod
    def _process_creation_payment(cls, op, amount_paid, officer, date):
        """Process the operation's payment (stage 2 of ``create``)."""
        from decimal import Decimal

        paid = Decimal(amount_paid) if amount_paid is not None else Decimal("0.00")
        if cls.can_pay and paid > Decimal("0.00"):
            op.process_payment(
                amount_paid=paid,
                officer=officer,
                date=date,
            )

    @classmethod
    def _process_creation_invoice(cls, op, operation_type, raw_post, project):
        """Process the operation's invoice / inventory (stage 3 of ``create``)."""
        if not cls.has_invoice or raw_post is None:
            return

        from apps.app_inventory.forms import (
            InvoiceItemCreateFormSet,
            InvoiceItemSelectFormSet,
        )

        # Determine the correct formset class
        formset_cls = (
            InvoiceItemCreateFormSet
            if cls.creates_assets
            else InvoiceItemSelectFormSet
        )
        # Rebind to the saved instance
        formset_kwargs = {"data": raw_post, "instance": op}
        if cls.creates_assets:
            formset_kwargs["project"] = project
            formset_kwargs["is_birth"] = operation_type == OperationType.BIRTH
        else:
            # Select-mode operations (SALE/DEATH/CONSUMPTION/CAPITAL):
            # restrict product selection to the owning entity so stock
            # from another project cannot be moved/written off.
            formset_kwargs["entity"] = op.inventory_owner_entity

        bound_formset = formset_cls(**formset_kwargs)
        bound_formset.is_valid()  # already validated earlier — this is a rebind
        bound_formset.save()
        op.save_inventory(bound_formset)

    @classmethod
    def get_related_entities(cls, url_entity, config):
        """Default candidate-entity set for the create form's destination picker."""
        from apps.app_entity.models import Entity

        config_dest = config["dest"]
        if config_dest in ["world", "url"]:
            return []
        elif config_dest == "post":
            return Entity.objects.all()
        return []

    # ------------------------------------------------------------------
    # Reversal helpers
    # ------------------------------------------------------------------

    def _reverse_period(self):
        """Allow the reversal to set in a different period than the original.
        Open periods are those with no end_date or a future end_date."""
        from .period import FinancialPeriod

        entity = self.period_entity
        if entity:
            return (
                FinancialPeriod.objects.filter(entity=entity)
                .filter(Q(end_date__isnull=True) | Q(end_date__gte=today_date.today()))
                .first()
            )
        return None

    @property
    def _reversable_transaction_types(self) -> List[TransactionType]:
        """Transaction types that must be reversed together with the operation."""
        rv = []
        # Non-accounting operations (Birth / Death / Consumption / Capital)
        # do not define *_transaction_type attrs — getattr keeps them empty.
        if getattr(self, "_issuance_transaction_type", None):
            rv.append(self._issuance_transaction_type)
        if getattr(self, "_payment_transaction_type", None):
            rv.append(self._payment_transaction_type)
        return rv

    @property
    def _implicit_reversable_transaction_types(self) -> List[TransactionType]:
        """Transaction types reversed implicitly (issuance; one-shot payment too)."""
        rv = []
        if getattr(self, "_issuance_transaction_type", None):
            rv.append(self._issuance_transaction_type)
        if getattr(self, "_is_one_shot_operation", False) and getattr(
            self, "_payment_transaction_type", None
        ):
            rv.append(self._payment_transaction_type)
        return rv

    # ------------------------------------------------------------------
    # Period helpers
    # ------------------------------------------------------------------

    @property
    def period_entity(self):
        """
        Returns the URL-role entity — the entity whose financial period this
        operation belongs to. Determined by _source_role / _dest_role set on
        each proxy class.
        """
        if self._source_role == "url":
            return self.source
        if self._dest_role == "url":
            return self.destination
        return None

    def cast(self):
        """Re-cast this instance to its operation proxy subclass."""
        return Operation.objects.cast(self)

    @property
    def effective_amount(self):
        """
        Effective amount for the non-accounting operations (Birth / Death /
        Consumption / Capital Gain / Capital Loss): these are not adjustable, so
        the effective amount is simply the operation ``amount``. Adjustable
        operations (Purchase / Sale / Expense) override this via
        ``AdjustableMixin`` to include their active adjustments.
        """
        return self.amount

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        """Validate entity activity, closed periods, and category requirements."""
        logger.debug(
            f"Operation.clean() ({self.operation_type}) | "
            f"is_new={self.pk is None} | pk={self.pk} | date={self.date}"
        )

        from django.utils.translation import gettext as _

        # Explicit entity-active check — independent of the fund-active mixins, so the
        # guarantee survives if a future operation's fund mapping ever diverges from its
        # source/destination entity. System/World entities are always active, so the
        # virtual-party operations (Birth/Death/Correction/Cash with system/world) are
        # unaffected.
        for entity in (self.source, self.destination):
            if entity is None:
                continue
            if not entity.active:
                logger.error(
                    f"Inactive entity on operation | entity={entity} | active={entity.active}"
                )
                raise ValidationError(
                    _("Entity '%(name)s' must be active to participate in this operation.")
                    % {"name": entity}
                )
        # Only block NEW, non-reversal operations from landing in a closed period.
        if not self.pk and not getattr(self, "reversal_of_id", None):
            from .period import is_date_in_closed_period

            # Check both source and destination entities.
            for entity in [self.source, self.destination]:
                if entity and is_date_in_closed_period(entity, self.date):
                    logger.error(
                        f"Cannot create operation in closed period | "
                        f"date={self.date} | entity={entity}"
                    )
                    raise ValidationError(
                        "Cannot create an operation whose date falls within a closed financial period."
                    )
        # Category enforcement — only applies when the proxy opts in via the
        # class-level config (e.g. ExpenseOperation: has_category=True). When a
        # proxy declares a category, selecting one is mandatory.
        if self.has_category and not self.category_id:
            logger.error(
                f"Missing required category on operation | "
                f"operation_type={self.operation_type}"
            )
            raise ValidationError(
                _("Category is required for this operation.")
            )
        logger.debug("Operation validation passed")
        return super().clean()

    def save(self, *args, **kwargs):
        """Auto-assign the covering financial period, then save and validate items."""
        is_new = self.pk is None

        # Auto-assign the period that contains this operation's date (never creates one).
        if (
            self.pk is None
            and self.period_id is None
            and not getattr(self, "reversal_of_id", None)
        ):
            entity = self.period_entity
            if entity:
                from django.db.models import Q

                from .period import FinancialPeriod

                self.period = (
                    FinancialPeriod.objects.filter(
                        entity=entity,
                        start_date__lte=self.date,
                    )
                    .filter(Q(end_date__isnull=True) | Q(end_date__gt=self.date))
                    .first()
                )
                if self.period is None:
                    raise ValidationError(
                        "Cannot create an operation: no financial period covers this operation's date."
                    )

        def _validate_invoice_items(op):
            items = op.items.all()
            logger.debug(
                f"Validating {items.count()} invoice items | operation_pk={op.pk}"
            )
            for item in items:
                item.full_clean()
            logger.debug(f"All {items.count()} invoice items validated")

        kwargs.setdefault("post_save_tasks", []).append(
            (
                _validate_invoice_items,
                (self,),
                {},
            )
        )

        result = super().save(*args, **kwargs)
        logger.debug(f"Operation saved | pk={self.pk}")

        # Audit log the operation
        action = "operation_created" if is_new else "operation_updated"
        audit_logger.info(
            f"{action} | Operation:{self.pk} | user={self.officer} | "
            f"type={self.operation_type} | source={self.source} | "
            f"destination={self.destination} | amount={float(self.amount)} | "
            f"date={self.date}"
        )
        return result

    # ------------------------------------------------------------------
    # Payment processing
    # ------------------------------------------------------------------

    def process_payment(self, amount_paid, officer, date=None, description=None):
        """
        Validate and record a payment transaction for this operation.

        Checks:
        - Payment only applies if the proxy class sets ``can_pay = True``.
        - Paid amount must not exceed the operation total.
        - If the proxy does not allow partial payment (``is_partially_payable``),
          the paid amount must equal the full total.
        - Creates the payment transaction via ``create_payment_transaction()``.
        """
        from decimal import Decimal

        from django.utils.translation import gettext as _

        if not type(self).can_pay:
            return

        amount_paid = (
            Decimal(amount_paid)
            if not isinstance(amount_paid, Decimal)
            else amount_paid
        )

        if amount_paid > self.amount:
            raise ValueError(
                _("Error: paid amount %(paid)s is more than the total %(total)s")
                % {"paid": amount_paid, "total": self.amount}
            )
        if not type(self).is_partially_payable and amount_paid < self.amount:
            raise ValueError(
                _("You can't pay less than %(amount)s for this operation.")
                % {"amount": self.amount}
            )
        if amount_paid > 0:
            self.create_payment_transaction(
                amount_paid,
                officer,
                date=date or self.date,
                description=description
                or _("Instant payment for the operation %(op_type)s %(pk)s")
                % {"op_type": self.operation_type, "pk": self.pk},
            )

    def settlement_summary(self):
        """
        Build the settlement display data used by the operations list.

        Operations fall into three kinds with different settlement semantics:
          - repayed  - recovered over time via repayments (loan, worker advance)
          - paid     - settled over time via payments (purchase, sale, expense)
          - one_shot - settled in full at creation (cash flows, funding, capital,
                       corrections, birth/death/consumption, internal transfers)

        Non-accounting operations (Birth/Death/Consumption/Capital) have no
        settlement mixin — the ``getattr`` guards keep them fully settled.

        Returns a dict with ``kind``, ``paid``, ``remaining``, ``total``,
        ``fully_settled`` and ``percent``.
        """
        from decimal import Decimal

        total = self.effective_amount or Decimal("0.00")

        if self.has_repayment:
            kind = "repayed"
            paid = getattr(self, "amount_repayed", None) or Decimal("0.00")
            remaining = getattr(self, "amount_remaining_to_repay", None) or Decimal(
                "0.00"
            )
            fully_settled = bool(getattr(self, "is_fully_repayed", False))
        elif self.is_partially_payable:
            kind = "paid"
            paid = getattr(self, "amount_settled", None) or Decimal("0.00")
            remaining = getattr(self, "amount_remaining_to_settle", None) or Decimal(
                "0.00"
            )
            fully_settled = bool(getattr(self, "is_fully_settled", False))
        else:
            # One-shot operations settle fully at creation (reversal voids it).
            kind = "one_shot"
            paid = getattr(self, "amount_settled", None) or total
            remaining = Decimal("0.00")
            fully_settled = bool(getattr(self, "is_fully_settled", True))

        if remaining < Decimal("0.00"):
            remaining = Decimal("0.00")

        percent = 0
        if total > Decimal("0.00"):
            percent = min(int(round(float(paid) / float(total) * 100)), 100)

        return {
            "kind": kind,
            "paid": paid,
            "remaining": remaining,
            "total": total,
            "fully_settled": fully_settled,
            "percent": percent,
        }

    def payment_balance(self):
        """
        Compute the payment-balance summary shown on the operation detail page.

        Non-accounting operations (Birth / Death / Consumption / Capital Gain /
        Capital Loss) do not track settlement — they are fully settled at their
        amount, so only accounting operations expose the settlement mixin
        members. Every access is guarded.

        Returns a dict of float values: ``paid_amount``, ``outstanding_balance``,
        ``net_adjustment``, ``overpayment_amount`` and ``over_repayment_amount``.
        """
        from decimal import Decimal

        has_settlement = hasattr(self, "amount_settled")
        paid_amount = float(
            self.amount_settled if has_settlement else self.amount
        )
        outstanding_balance = float(
            self.amount_remaining_to_settle
            if has_settlement
            else Decimal("0.00")
        )
        net_adjustment = float(
            (self.effective_amount or Decimal("0.00")) - self.amount
        )
        overpayment_amount = float(
            self.amount_settled - self.total_settlable_amount
            if has_settlement and self.is_overpayed_settled
            else Decimal("0.00")
        )
        over_repayment_amount = float(
            self.amount_repayed - self.repayable_amount
            if getattr(self, "is_overpaid_repayed", False)
            else Decimal("0.00")
        )
        return {
            "paid_amount": paid_amount,
            "outstanding_balance": outstanding_balance,
            "net_adjustment": net_adjustment,
            "overpayment_amount": overpayment_amount,
            "over_repayment_amount": over_repayment_amount,
        }

    def reverse(self, officer, date=None, reason=None):
        """Reverse an operation with full audit trail."""
        import uuid

        from django.utils.translation import gettext as _

        txn_id = f"reverse_op_{self.pk}_{uuid.uuid4().hex[:8]}"
        audit_logger.info(
            f"transaction_start | reverse_txn={txn_id} | reversing Operation:{self.pk} | "
            f"operation_type={self.operation_type} | amount={float(self.amount)}"
        )

        try:
            # Reversal dependency guard (inventory mixin): do not reverse an
            # operation whose products were moved again in a later non-reversed
            # outbound operation. The type dispatch lives with the other
            # inventory logic in ``InventoryOperationMixin``.
            self._validate_reversal_inventory_guards()

            reversal = super().reverse(officer=officer, date=date, reason=reason)

            # Reverse the operation's inventory (inventory mixin): PURCHASE /
            # SALE require the user to reverse user-driven movements first;
            # BIRTH / DEATH / CONSUMPTION reverse their tightly-coupled
            # auto-created movements automatically.
            if type(self).has_invoice:
                self._reverse_inventory_movements(officer=officer, date=date)

            audit_logger.info(
                f"transaction_commit | reverse_txn={txn_id} | original_op={self.pk} | "
                f"reversal_op={reversal.pk} | status=success"
            )

            audit_logger.info(
                f"operation_reversed | Operation:{self.pk} | user={officer} | "
                f"type={self.operation_type} | reversal_pk={reversal.pk} | "
                f"reason={reason or ''}"
            )

            return reversal
        except Exception as e:
            audit_logger.error(
                f"operation_reversal_failed | Operation:{self.pk} | user={officer} | "
                f"error={e} | reason={reason or ''}"
            )
            raise

    def __str__(self):
        return (
            f"Operation {self.operation_type}: "
            f"{self.amount} from {self.source} to {self.destination}"
        )


# --------------------------------------------------------------------------
# Mixin stacks for accounting-capable operations
#
# ``Operation`` is intentionally lean: Birth / Death / Consumption / Capital
# Gain / Capital Loss are stock events, not accounting operations, so they do
# not inherit the transaction / settlement / repayment / adjustment machinery.
# The accounting-capable proxies instead compose the relevant mixins through
# the plain (non-model) mixin stacks below and keep a single concrete parent
# (``Operation``), so no extra tables are created (all proxies stay ``proxy=True``).
# --------------------------------------------------------------------------


class TransactionMixin(
    LinkedIssuanceTransactionMixin, LinkedPaymentTransactionMixin
):
    """Issuance + payment transaction behavior (all accounting operations)."""


class OneShotTransactionMixin(TransactionMixin):
    """One-shot operations settle in full at creation.

    A one-shot operation writes an issuance transaction plus exactly one payment
    transaction atomically at ``save()`` (the pay action is ``E@create`` per the
    operation specs — there is no standalone pay action). It is not partially
    payable, has no category, and is not repayable by default.
    """

    _is_one_shot_operation = True
    max_payment_transaction_count = 1
    can_pay = False
    is_partially_payable = False


class AdjustableTransactionMixin(AdjustableMixin, TransactionMixin):
    """Adds accounting / item adjustment behavior (Purchase, Sale, Expense)."""


class RepayableTransactionMixin(LinkedRePaymentTransactionMixin, TransactionMixin):
    """Adds repayment behavior (Loan, Worker Advance)."""


class StockEventMixin:
    """Stock-event operations — inventory-only, no accounting transactions.

    Shared config for the auto-movement operations (Birth, Death, Consumption)
    and the value-only capital valuations (Capital Gain / Capital Loss): never
    payable, no category, no repayment. Invoice-driven by default —
    ``CapitalValuationOperation`` overrides ``has_invoice = False`` because it
    is value-only (a ``ProductCapitalValuation`` row, no invoice items).
    """

    can_pay = False
    check_balance_on_payment = False
    is_partially_payable = False
    has_category = False
    has_repayment = False
    has_invoice = True
