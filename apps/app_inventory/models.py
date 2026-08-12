from datetime import date as today_date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.utils.translation import gettext_lazy as _

from apps.app_base.debug import DebugContext
from apps.app_base.mixins import AmountCleanMixin, ImmutableMixin
from apps.app_base.models import BaseModel


class ProductTemplate(BaseModel):
    class TrackingMode(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", _("Individual (Tag ID)")
        COMMODITY = "COMMODITY", _("Quantity (Weight/Volume)")

    class Nature(models.TextChoices):
        ANIMAL = "ANIMAL", _("Livestock Asset")
        FEED = "FEED", _("Consumable")
        MEDICINE = "MEDICINE", _("Biological")
        PRODUCT = "PRODUCT", _("Production Output")

    name = models.CharField(_("name"), max_length=100)  # e.g., "Fattening Calves"
    name_ar = models.CharField(_("name (Arabic)"), max_length=100, blank=True)
    nature = models.CharField(
        _("nature"), choices=Nature.choices, max_length=20, default=Nature.ANIMAL
    )

    sub_category = models.CharField(
        _("sub_category"),
        max_length=20,
        default=_("General"),
    )

    default_unit = models.CharField(
        _("default unit"), max_length=20, default="Head"
    )  # e.g., "Head", "Kg"
    has_tag = models.BooleanField(_("has tag"), default=False)
    tag_prefix = models.CharField(
        _("tag prefix"),
        max_length=20,
        blank=True,
        default="",
        help_text=_(
            "Prefix used to auto-generate unique tags for individually tracked "
            "animals (e.g. CALF, COW, LAMB). If blank, it is derived from the "
            "template name."
        ),
    )
    minimum_quantity = models.DecimalField(
        _("minimum quantity"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text=_(
            "Smallest allowed quantity increment. Used as the `step` attribute on number inputs in forms "
            "and enforced on invoice/movement quantities (e.g. 1 for Head, 0.01 for Kg)."
        ),
    )

    tracking_mode = models.CharField(
        _("tracking mode"),
        choices=TrackingMode.choices,
        max_length=24,
        default=TrackingMode.INDIVIDUAL,
        help_text=_(
            "Resolved automatically from nature: ANIMAL → INDIVIDUAL, otherwise "
            "COMMODITY."
        ),
    )

    # ------------------------------------------------------------------
    # Animal-specific attributes (only meaningful when nature == ANIMAL)
    # ------------------------------------------------------------------

    class Gender(models.TextChoices):
        MALE = "MALE", _("Male")
        FEMALE = "FEMALE", _("Female")
        MIXED = "MIXED", _("Mixed")
        NA = "NA", _("Not applicable")

    animal_type = models.CharField(
        _("animal type"),
        max_length=50,
        blank=True,
        default="",
        help_text=_("Species/type of animal, e.g. Cow, Buffalo, Sheep, Goat."),
    )
    gender = models.CharField(
        _("gender"),
        choices=Gender.choices,
        max_length=10,
        default=Gender.NA,
        help_text=_(
            "Default gender for animals created from this template "
            "(MALE/FEMALE/MIXED). NA for non-animal templates."
        ),
    )
    produces = models.ManyToManyField(
        "self",
        related_name="produced_by",
        verbose_name=_("produces"),
        blank=True,
        symmetrical=False,
        help_text=_(
            "Output templates this animal can produce (e.g. Milk, Manure). "
            "Metadata only — no production operation yet."
        ),
    )
    gives_birth_to = models.ForeignKey(
        "self",
        related_name="born_from",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("gives birth to"),
        help_text=_(
            "Offspring template produced at birth (e.g. Dairy Cow → Calf). "
            "Only valid for ANIMAL templates with gender FEMALE or MIXED."
        ),
    )
    can_die = models.BooleanField(
        _("can die"),
        default=True,
        help_text=_("Whether this product can die. All animals can die."),
    )
    can_be_consumed = models.BooleanField(
        _("can be consumed"),
        default=True,
        help_text=_(
            "Whether this product can be consumed. No animal can be consumed "
            "(forced to False for ANIMAL templates)."
        ),
    )

    # TODO: only project entities are allowed
    entities = models.ManyToManyField(
        "app_entity.Entity",
        related_name="product_templates",
        verbose_name=_("entities"),
        blank=True,
    )

    _ALLOWED_OP_TYPES: dict[str, frozenset] = {
        "ANIMAL": frozenset(
            {"PURCHASE", "SALE", "BIRTH", "DEATH", "CAPITAL_GAIN", "CAPITAL_LOSS"}
        ),
        "FEED": frozenset(
            {"PURCHASE", "SALE", "CONSUMPTION", "CAPITAL_GAIN", "CAPITAL_LOSS"}
        ),
        "MEDICINE": frozenset(
            {"PURCHASE", "SALE", "CONSUMPTION", "CAPITAL_GAIN", "CAPITAL_LOSS"}
        ),
        "PRODUCT": frozenset({"PURCHASE", "SALE", "CAPITAL_GAIN", "CAPITAL_LOSS"}),
    }

    def accepts_operation(self, op_type: str) -> bool:
        from apps.app_operation.models.operation_type import OperationType

        allowed = self._ALLOWED_OP_TYPES.get(self.nature, frozenset())
        if op_type not in allowed:
            return False
        # Flag-level gating on top of the nature-based allow-list.
        if op_type == OperationType.DEATH and not self.can_die:
            return False
        if op_type == OperationType.CONSUMPTION and not self.can_be_consumed:
            return False
        return True

    @classmethod
    def tracking_mode_for_nature(cls, nature) -> str:
        """Nature-based tracking mode: ANIMAL → INDIVIDUAL, else → COMMODITY."""
        if nature == cls.Nature.ANIMAL:
            return cls.TrackingMode.INDIVIDUAL
        return cls.TrackingMode.COMMODITY

    def clean(self) -> None:
        # Tracking mode is derived from nature — there is no free choice.
        if self.nature:
            self.tracking_mode = self.tracking_mode_for_nature(self.nature)

        if self.nature == self.Nature.ANIMAL:
            # No animal can ever be consumed — force the flag off.
            self.can_be_consumed = False
            # A template that gives birth must be a female/mixed animal and its
            # offspring must itself be an animal template.
            if self.gives_birth_to is not None:
                if self.gives_birth_to.nature != self.Nature.ANIMAL:
                    raise ValidationError(
                        _("'gives birth to' must reference an ANIMAL template.")
                    )
                if self.gender not in (self.Gender.FEMALE, self.Gender.MIXED):
                    raise ValidationError(
                        _(
                            "Only templates with gender FEMALE or MIXED can give "
                            "birth."
                        )
                    )
            # 'produces' may only reference output (FEED/PRODUCT) templates.
            # M2M is only queryable once the instance is persisted.
            if self.pk is not None and self.produces.exists():
                bad = self.produces.exclude(
                    nature__in=(self.Nature.FEED, self.Nature.PRODUCT)
                )
                if bad.exists():
                    raise ValidationError(
                        _(
                            "'produces' may only reference FEED or PRODUCT "
                            "templates."
                        )
                    )
        else:
            # Non-animals don't die (they aren't livestock).
            if self.can_die:
                self.can_die = False

        return super().clean()

    @property
    def effective_tag_prefix(self) -> str:
        """Uppercase prefix used for auto-generated animal tags."""
        prefix = (self.tag_prefix or "").strip().upper()
        if prefix:
            return prefix
        # Derive a short prefix from the template name (e.g. "Calves" → "CALV").
        chars = "".join(c for c in self.name.upper() if c.isalnum())[:4]
        return chars or "AN"

    def next_tag(self, entity) -> str:
        """
        Next suggested unique tag for *entity* on this template:
        ``{PREFIX}{max_existing_numeric_suffix + 1}`` (1 when none exist).

        Uses ``all_objects`` (includes soft-deleted rows) so the suggested tag
        never collides with the DB UniqueConstraint on ``(entity, unique_id)``,
        which applies to every row regardless of soft-deletion.  The caller may
        edit the suggested value; the constraint is the hard backstop.
        """
        from apps.app_inventory.models import Product

        prefix = self.effective_tag_prefix
        existing = Product.all_objects.filter(
            entity=entity, product_template=self, unique_id__startswith=prefix
        ).values_list("unique_id", flat=True)
        max_num = 0
        for uid in existing:
            suffix = uid[len(prefix):] if uid else ""
            if suffix.isdigit():
                max_num = max(max_num, int(suffix))
        return f"{prefix}{max_num + 1}"

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("product template")
        verbose_name_plural = _("product templates")
        unique_together = (
            "name",
            "nature",
            "sub_category",
            "default_unit",
            "tracking_mode",
            "has_tag",
        )


class InvoiceItem(AmountCleanMixin, BaseModel):
    _amount_name = "quantity"

    operation = models.ForeignKey(
        "app_operation.Operation",
        related_name="items",
        on_delete=models.CASCADE,
        verbose_name=_("operation"),
    )
    product_template = models.ForeignKey(
        ProductTemplate,
        on_delete=models.PROTECT,
        related_name="invoice_items",
        verbose_name=_("product template"),
        db_column="product_id",
    )
    description = models.TextField(_("description"), blank=True)
    quantity = models.DecimalField(
        _("quantity"), max_digits=10, decimal_places=2, default=1
    )
    unit_price = models.DecimalField(_("unit price"), max_digits=15, decimal_places=2)

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    # ------------------------------------------------------------------
    # Adjustment-aware properties
    # ------------------------------------------------------------------

    @property
    def adjusted_quantity(self) -> Decimal:
        """Effective quantity = most recent ``new_quantity`` from active
        (non-reversed) adjustment lines, or original if none."""
        last_qty = (
            self.item_adjustment_lines.filter(
                adjustment__reversed_by__isnull=True, new_quantity__isnull=False
            )
            .order_by("-pk")
            .values_list("new_quantity", flat=True)
            .first()
        )
        return last_qty if last_qty is not None else self.quantity

    @property
    def adjusted_unit_price(self) -> Decimal:
        """Effective unit price = most recent ``new_unit_price`` from active
        (non-reversed) adjustment lines, or original if none."""
        last_price = (
            self.item_adjustment_lines.filter(
                adjustment__reversed_by__isnull=True, new_unit_price__isnull=False
            )
            .order_by("-pk")
            .values_list("new_unit_price", flat=True)
            .first()
        )
        return last_price if last_price is not None else self.unit_price

    @property
    def adjusted_total_price(self) -> Decimal:
        """Effective total after all adjustments = adjusted_qty * adjusted_price."""
        return self.adjusted_quantity * self.adjusted_unit_price

    @property
    def adjustment_quantity_delta(self) -> Decimal:
        """Net change from original quantity to effective adjusted quantity."""
        return self.adjusted_quantity - self.quantity

    @property
    def adjustment_value_delta(self) -> Decimal:
        """Net change from original total to effective adjusted total."""
        return self.adjusted_total_price - self.total_price

    @property
    def has_adjustments(self) -> bool:
        """Whether any active (non-reversed) adjustment lines exist for this item."""
        return self.item_adjustment_lines.filter(
            adjustment__reversed_by__isnull=True
        ).exists()

    def clean_unit_price(self):
        if self.unit_price < 0:
            raise ValidationError(_("Unit price cannot be negative"))

    def clean(self) -> None:
        # TODO: not well implemented,
        # The operation_type is empty
        try:
            op_type = self.operation.operation_type
            if not op_type:
                return super().clean()

        except Exception as e:
            return super().clean()
        if not self.product_template.accepts_operation(op_type):
            raise ValidationError(
                _(
                    "'%(product)s' (%(nature)s) cannot be used in a %(op_type)s operation."
                )
                % {
                    "product": self.product_template.name,
                    "nature": self.product_template.get_nature_display(),
                    "op_type": op_type,
                }
            )
        # Unit consistency: quantity must be a positive multiple of the
        # template's minimum quantity increment (e.g. 1 for Head, 0.01 for Kg)
        # to prevent kg/head mistakes at contract (invoice) level.
        min_qty = self.product_template.minimum_quantity
        if min_qty and min_qty > 0 and (self.quantity % min_qty) != 0:
            raise ValidationError(
                _(
                    "Quantity %(qty)s must be a multiple of the minimum "
                    "increment %(min)s for '%(p)s'."
                )
                % {
                    "qty": self.quantity,
                    "min": min_qty,
                    "p": self.product_template,
                }
            )
        return super().clean()

    # ------------------------------------------------------------------
    # Pending-items lookup  (use stock.pending_items() instead)
    #
    # Previously had unreceived_purchases() and undelivered_sales() here,
    # but those used .exclude() on movement lines — broken for partial
    # deliveries.  Replaced by apps.app_inventory.stock.pending_items().
    # ------------------------------------------------------------------

    @classmethod
    def create_products_for_item(
        cls,
        invoice_item,
        entity,
        quantity,
        unit_price,
        unique_id=None,
        gender=None,
        birth_date=None,
        mother=None,
    ):
        """
        Create Product record(s) for *invoice_item* based on the template's
        tracking mode, owned by *entity*.

        **INDIVIDUAL** → one ``Product`` per head (qty=1 each), each with its
        own unique tag.  A provided ``unique_id`` is used for the first head;
        any remaining heads get an auto-generated tag via
        ``template.next_tag(entity)`` so every animal is uniquely identified.

        **COMMODITY** → a single ``Product`` with the full quantity (bulk).

        Animal attributes:
        - ``gender`` (optional): MALE/FEMALE; when omitted, defaults to the
          template's gender when it is MALE/FEMALE, otherwise UNKNOWN.
        - ``birth_date`` (optional): set on the created animal (e.g. from a
          birth operation).
        - ``mother`` (optional): the Product that gave birth to this animal.

        Returns the list of created ``Product`` instances.
        """
        from apps.app_inventory.models import Product

        template = invoice_item.product_template
        qty = int(quantity)  # Product.quantity is PositiveIntegerField
        products = []

        if gender in (Product.Gender.MALE, Product.Gender.FEMALE):
            resolved_gender = gender
        elif template.gender in (Product.Gender.MALE, Product.Gender.FEMALE):
            resolved_gender = template.gender
        else:
            resolved_gender = Product.Gender.UNKNOWN

        animal_kwargs = {
            "gender": resolved_gender,
            "birth_date": birth_date,
            "mother": mother,
        }

        if template.tracking_mode == ProductTemplate.TrackingMode.INDIVIDUAL:
            # One Product per head — each gets its own unique tag.
            for i in range(max(qty, 1)):
                uid = unique_id if i == 0 else None
                if not uid:
                    uid = template.next_tag(entity)
                product = Product.objects.create(
                    entity=entity,
                    product_template=template,
                    quantity=1,
                    unit_price=unit_price,
                    unique_id=uid,
                    **animal_kwargs,
                )
                product.invoice_items.add(invoice_item)
                products.append(product)
        else:
            # COMMODITY — single Product with full quantity
            product = Product.objects.create(
                entity=entity,
                product_template=template,
                quantity=qty,
                unit_price=unit_price,
                unique_id=unique_id,
                **animal_kwargs,
            )
            product.invoice_items.add(invoice_item)
            products.append(product)

        return products

    @classmethod
    def build_movement_json(cls, operation):
        """
        Build a JSON-serialisable dict of invoice-item data for the
        inventory-movement form.  Each key is the invoice-item PK; each
        value contains ``quantity``, ``already_moved`` and ``max_allowed``.
        """
        import json

        from django.db.models import Q, Sum

        # Direction-aware: for an outbound op (SALE) only the movements of the
        # dispatching entity count as "already moved" — an internal-client
        # sale also carries the buyer's receipt on the same invoice item.
        owner = operation.inventory_owner_entity
        already_filter = Q(movement_lines__reversal_of__isnull=True)
        if owner is not None:
            already_filter &= Q(movement_lines__product__entity=owner)
        # Originals that have since been reversed no longer count as moved.
        reversed_originals = InventoryMovementLine.objects.filter(
            invoice_item__operation=operation, reversal_of__isnull=False
        ).values_list("reversal_of_id", flat=True)
        already_filter &= ~Q(movement_lines__id__in=list(reversed_originals))

        items = cls.objects.filter(operation=operation).annotate(
            already_moved=Sum(
                "movement_lines__quantity",
                filter=already_filter,
            )
        )
        data = {}
        for item in items:
            already_moved = item.already_moved or Decimal("0.00")
            data[item.pk] = {
                "quantity": float(item.quantity),
                "already_moved": float(already_moved),
                "max_allowed": float(item.quantity - already_moved),
            }
        return json.dumps(data)

    def __str__(self):
        return f"{self.product_template.name} ({self.quantity})"

    class Meta:
        verbose_name = _("invoice item")
        verbose_name_plural = _("invoice items")


class Product(AmountCleanMixin, BaseModel):
    _amount_name = "unit_price"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Active")
        SOLD = "SOLD", _("Sold")
        DEAD = "DEAD", _("Dead")
        CONSUMED = "CONSUMED", _("Consumed")
        REMOVED = "REMOVED", _("Removed")

    entity = models.ForeignKey(
        "app_entity.Entity",
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("entity"),
        null=True,
        blank=True,
    )
    product_template = models.ForeignKey(
        ProductTemplate, on_delete=models.PROTECT, verbose_name=_("product template")
    )
    invoice_items = models.ManyToManyField(
        InvoiceItem, related_name="products", verbose_name=_("invoice items")
    )
    unique_id = models.CharField(
        _("unique id"), max_length=50, db_index=True, null=True, blank=True
    )
    quantity = models.PositiveIntegerField(_("quantity"), default=1)
    unit_price = models.DecimalField(_("unit price"), max_digits=15, decimal_places=2)
    notes = models.TextField(_("notes"), blank=True)

    # --- Per-animal attributes (only meaningful for ANIMAL templates) ---
    class Gender(models.TextChoices):
        MALE = "MALE", _("Male")
        FEMALE = "FEMALE", _("Female")
        UNKNOWN = "UNKNOWN", _("Unknown")

    gender = models.CharField(
        _("gender"),
        choices=Gender.choices,
        max_length=10,
        default=Gender.UNKNOWN,
        help_text=_("Individual animal sex; defaults from the template when born."),
    )
    birth_date = models.DateField(_("birth date"), null=True, blank=True)
    mother = models.ForeignKey(
        "self",
        related_name="offspring",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("mother"),
        help_text=_("Mother animal that gave birth to this animal."),
    )

    @property
    def is_physically_moved(self) -> bool:
        """
        True if this product has been physically moved into or out of stock
        (i.e. has at least one non-reversal InventoryMovementLine).
        """
        # Should we also check that the movement line's invoice item is not reversed? That would make sense, as a reversed invoice item would imply that the movement is no longer valid. The current implementation only checks for non-reversal movement lines, which may not account for the case where the associated invoice item has been reversed.   
        return self.movement_lines.filter(reversal_of__isnull=True).exists()

    @property
    def is_obligated_only(self) -> bool:
        """
        True if this product is registered (linked to an InvoiceItem) but has
        NOT yet been physically moved (no InventoryMovementLine records).
        Such products are "obligated" — committed on paper but not yet present.
        """
        return not self.is_physically_moved

    @property
    def movement_state_label(self) -> str:
        """Human-readable label for the movement state."""
        if self.is_physically_moved:
            return _("Physically Moved")
        return _("Obligated Only")

    @property
    def status(self) -> str:
        """
        Physical status derived from the product's own movement lines (the
        physical truth) rather than from linked operations.

        - net presence > 0  → ACTIVE
        - net presence ≤ 0 with a terminal outbound movement
          (SALE/DEATH/CONSUMPTION) → SOLD / DEAD / CONSUMED
        - no active movements → falls back to the linked-operation status
          (historical), so registered-but-unmoved products and restored
          (reversed) disposals keep prior semantics.
        """
        from apps.app_operation.models.operation_type import OperationType

        TERMINAL_STATUS = {
            OperationType.DEATH: self.Status.DEAD,
            OperationType.SALE: self.Status.SOLD,
            OperationType.CONSUMPTION: self.Status.CONSUMED,
        }

        # Movements still active: not a reversal line, and not the original of a
        # reversal line (i.e. not reversed).
        reversed_originals = InventoryMovementLine.objects.filter(
            product=self, reversal_of__isnull=False
        ).values_list("reversal_of_id", flat=True)
        active = list(
            self.movement_lines.filter(reversal_of__isnull=True)
            .exclude(id__in=list(reversed_originals))
            .select_related("operation")
            .order_by("date", "created_at")
        )

        if active:
            net = Decimal("0.00")
            last_terminal_type = None
            for ml in active:
                op_type = ml.operation.operation_type
                if op_type in (OperationType.PURCHASE, OperationType.BIRTH):
                    net += ml.quantity
                elif op_type in (OperationType.DEATH, OperationType.CONSUMPTION):
                    net -= ml.quantity
                    last_terminal_type = op_type
                elif op_type == OperationType.SALE:
                    if self.entity_id == ml.operation.source_id:
                        net += ml.quantity  # buyer receipt (internal transfer)
                    else:
                        net -= ml.quantity  # seller dispatch
                        last_terminal_type = op_type
            if net > Decimal("0.00"):
                return self.Status.ACTIVE
            if last_terminal_type is not None:
                return TERMINAL_STATUS[last_terminal_type]
            return self.Status.ACTIVE

        return self._status_from_linked_operations()

    def _status_from_linked_operations(self) -> str:
        """
        Historical status derived from the linked operations — used when a
        product has no active movements (registered-but-unmoved items, or a
        reversal that restored stock). Direction-aware: receiver side → ACTIVE,
        disposer side → terminal.
        """
        from apps.app_operation.models.operation_type import OperationType

        STATUS_CHANGING_TYPES = {
            OperationType.PURCHASE,
            OperationType.BIRTH,
            OperationType.DEATH,
            OperationType.SALE,
            OperationType.CONSUMPTION,
        }
        RECEIVER_SIDE = {
            OperationType.PURCHASE: "source",     # the buying project receives
            OperationType.BIRTH: "destination",   # the project receives
            OperationType.SALE: "source",         # the internal client receives
        }
        DISPOSER_SIDE = {
            OperationType.SALE: "destination",    # the seller dispatches
            OperationType.DEATH: "source",        # the project writes off
            OperationType.CONSUMPTION: "source",  # the project consumes
        }
        TERMINAL_STATUS = {
            OperationType.DEATH: self.Status.DEAD,
            OperationType.SALE: self.Status.SOLD,
            OperationType.CONSUMPTION: self.Status.CONSUMED,
        }
        TYPE_TO_STATUS = {
            OperationType.PURCHASE: self.Status.ACTIVE,
            OperationType.BIRTH: self.Status.ACTIVE,
            OperationType.DEATH: self.Status.DEAD,
            OperationType.SALE: self.Status.SOLD,
            OperationType.CONSUMPTION: self.Status.CONSUMED,
        }

        last_item = (
            self.invoice_items.filter(
                operation__operation_type__in=STATUS_CHANGING_TYPES,
                operation__reversed_by__isnull=True,
                operation__reversal_of__isnull=True,
            )
            .select_related("operation", "operation__source", "operation__destination")
            .order_by("-operation__date", "-operation__created_at")
            .first()
        )

        if last_item is None:
            # A product whose only entry into stock was a reversed BIRTH no
            # longer belongs in stock → REMOVED.
            if self.invoice_items.filter(
                operation__operation_type=OperationType.BIRTH,
                operation__reversed_by__isnull=False,
            ).exists():
                return self.Status.REMOVED
            return self.Status.ACTIVE

        op = last_item.operation
        op_type = op.operation_type

        receiver_side = RECEIVER_SIDE.get(op_type)
        if receiver_side is not None:
            receiver = getattr(op, receiver_side)
            if receiver is not None and self.entity_id == receiver.id:
                return self.Status.ACTIVE

        disposer_side = DISPOSER_SIDE.get(op_type)
        if disposer_side is not None:
            disposer = getattr(op, disposer_side)
            if disposer is not None and self.entity_id == disposer.id:
                return TERMINAL_STATUS[op_type]

        return TYPE_TO_STATUS[op_type]

    @property
    def current_value(self) -> Decimal:
        """
        Current book value — the movement-based valuation (the same basis
        financial-period inventory uses). For a product with no movements yet it
        is the nominal carried value (unit_price × quantity).
        """
        from apps.app_inventory.stock import movement_state

        if self.is_physically_moved:
            return movement_state(self, as_of=today_date.today())["value"]
        return self.unit_price * self.quantity

    def validate_active(
        self,
        allow_reversal: bool = False,
        allow_adjustment: bool = False,
        allow_obligated: bool = False,
    ) -> None:
        """
        Raise ValidationError if product can't participate in operations.

        SOLD/DEAD/CONSUMED/REMOVED products are forbidden in normal operations,
        but allowed in:
        - Reversals (allow_reversal=True): undoing a sale, death or consumption
        - Adjustments (allow_adjustment=True): correcting records

        Obligated-only products (registered but not physically moved) are
        forbidden in downstream operations (SALE, DEATH, CONSUMPTION, etc.),
        but allowed in:
        - Movement lines (allow_obligated=True): this IS the physical move
        - Reversals (allow_reversal=True)
        """
        status = self.status
        if status in (
            self.Status.SOLD,
            self.Status.DEAD,
            self.Status.CONSUMED,
            self.Status.REMOVED,
        ):
            if allow_reversal or allow_adjustment:
                return
            raise ValidationError(
                _(
                    "Product '%(id)s' has status %(status)s and cannot be used in new operations."
                )
                % {"id": self.unique_id or self.pk, "status": status}
            )

        # Block obligated-only products from downstream operations
        # (they are registered on an invoice item but haven't physically moved yet).
        if self.is_obligated_only and not allow_obligated and not allow_reversal:
            raise ValidationError(
                _(
                    "Product '%(id)s' is obligated only (registered but not "
                    "yet physically moved). It cannot be used in operations "
                    "until it has been moved into stock."
                )
                % {"id": self.unique_id or self.pk}
            )

    def clean(self) -> None:
        DebugContext.log(
            "Product.clean()",
            {
                "pk": self.pk,
                "product": self.product_template.name if self.product_template else "",
                "quantity": self.quantity,
                "status": self.status if self.pk else "new",
            },
        )
        super().clean()  # AmountCleanMixin: unit_price > 0
        # M2M is unavailable until the object has been persisted.
        if self.pk is None:
            DebugContext.success("Product validation passed (not yet persisted)")
            return
        for item in self.invoice_items.select_related("operation").all():
            op_type = item.operation.operation_type
            if not self.product_template.accepts_operation(op_type):
                DebugContext.error(
                    "Product incompatible with operation",
                    data={
                        "product": self.product_template.name,
                        "operation_type": op_type,
                    },
                )
                raise ValidationError(
                    _("Product '%(p)s' is not compatible with operation type %(op)s.")
                    % {"p": self.product_template.name, "op": op_type}
                )
        DebugContext.success("Product validation passed")

    def save(self, *args, **kwargs):
        """Save product with audit logging."""
        is_new = self.pk is None
        action = "created" if is_new else "updated"
        with DebugContext.section(
            f"Product.save() ({action})",
            {
                "product": self.product_template.name if self.product_template else "",
                "quantity": self.quantity,
                "unit_price": float(self.unit_price),
                "status": self.status if self.pk else "new",
            },
        ):
            result = super().save(*args, **kwargs)
            DebugContext.success(f"Product {action}", {"pk": self.pk})

            DebugContext.audit(
                action=f"product_{action}",
                entity_type="Product",
                entity_id=self.pk,
                details={
                    "product_template": (
                        self.product_template.name if self.product_template else ""
                    ),
                    "quantity": self.quantity,
                    "unit_price": float(self.unit_price),
                    "status": self.status,
                },
                user="system",
            )
            return result

    def delete(self, *args, **kwargs):
        """Delete product with audit logging."""
        with DebugContext.section(
            "Product.delete()",
            {
                "pk": self.pk,
                "product": self.product_template.name if self.product_template else "",
                "quantity": self.quantity,
                "status": self.status,
            },
        ):
            DebugContext.warn(
                "Deleting product",
                {
                    "pk": self.pk,
                    "product": (
                        self.product_template.name if self.product_template else ""
                    ),
                    "status": self.status,
                },
            )

            DebugContext.audit(
                action="product_deleted",
                entity_type="Product",
                entity_id=self.pk,
                details={
                    "product_template": (
                        self.product_template.name if self.product_template else ""
                    ),
                    "status": self.status,
                },
                user="system",
            )

            return super().delete(*args, **kwargs)

    # ------------------------------------------------------------------
    # Concurrency helpers
    # ------------------------------------------------------------------

    @classmethod
    def lock_ids(cls, product_ids):
        """
        Acquire row locks (``SELECT ... FOR UPDATE``) on the given products for
        the duration of the current transaction.

        Must be called inside an active ``atomic()`` block so the locks are held
        until commit — this serializes concurrent movements/checks on the same
        stock. On backends without row locking (e.g. SQLite) it is a no-op.

        Returns the locked ``Product`` instances as a list.
        """
        if not product_ids:
            return []
        return list(cls.objects.select_for_update().filter(id__in=product_ids))

    # ------------------------------------------------------------------
    # Valuation helpers
    # ------------------------------------------------------------------

    def compute_valuation_delta(self, new_unit_price: Decimal) -> dict:
        """
        Calculate the valuation delta when re-evaluating this product.

        Returns a dict with:
        - ``current_unit_price`` — the current per-unit value
        - ``delta`` — the total value change (new - current) * quantity
        """
        quantity = self.quantity
        current_value = self.current_value
        current_unit_price = (current_value / quantity) if quantity else Decimal("0.00")
        delta = (new_unit_price - current_unit_price) * (quantity or 1)
        return {
            "current_unit_price": current_unit_price,
            "delta": delta,
        }

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "unique_id"],
                condition=Q(unique_id__isnull=False),
                name="unique_product_tag_per_entity",
            )
        ]


class InventoryMovementLine(ImmutableMixin, BaseModel):
    """
    A flat record of a physical inventory movement (receipt or dispatch).

    Direction is implicit from the parent operation type (PURCHASE=inbound,
    SALE=outbound).  Reversal lines are linked via ``reversal_of`` and are
    excluded (together with their reversed originals) from the stock queries.

    Every line carries its own ``operation``, ``date``, ``officer`` and
    ``group_key`` directly — there is no separate ledger table anymore.
    """

    _immutable_fields = {
        "operation": {},
        "invoice_item": {},
        "quantity": {},
        "product": {},
    }

    operation = models.ForeignKey(
        "app_operation.Operation",
        on_delete=models.PROTECT,
        related_name="movement_lines",
        verbose_name=_("operation"),
    )
    invoice_item = models.ForeignKey(
        InvoiceItem,
        on_delete=models.PROTECT,
        related_name="movement_lines",
        verbose_name=_("invoice item"),
    )
    product = models.ForeignKey(
        "Product",
        on_delete=models.PROTECT,
        related_name="movement_lines",
        verbose_name=_("product"),
        null=True,
        blank=True,
    )
    quantity = models.DecimalField(
        _("quantity"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    date = models.DateField(_("date"), default=today_date.today)
    notes = models.TextField(_("notes"), blank=True)
    reversal_of = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversed_by",
        verbose_name=_("reversal of"),
    )
    group_key = models.CharField(
        _("group key"),
        max_length=32,
        blank=True,
        default="",
        help_text=_("Short hex string grouping lines created together."),
    )
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movement_lines_supervised",
        verbose_name=_("officer"),
        null=True,
        blank=True,
    )

    def _outbound_owner_entity(self):
        """
        The entity whose physical inventory this movement line reduces.

        Delegates to the operation's canonical ``inventory_owner_entity`` so the
        ownership mapping lives in one place. Returns None for inbound
        (PURCHASE/BIRTH) and non-inventory operations.

        Direction-aware: on a SALE, a movement line whose product is owned by the
        SALE **source** (an internal-client buyer receipt) is inbound — it has no
        outbound owner, so the ownership/availability guards do not apply.
        """
        from apps.app_operation.models.operation_type import OperationType

        if (
            self.operation_id is not None
            and self.operation.operation_type == OperationType.SALE
            and self.product_id is not None
            and self.product.entity_id == self.operation.source_id
        ):
            return None
        return self.operation.inventory_owner_entity

    def _validate_availability(self):
        """
        Raise ValidationError if this outbound (non-reversal) movement would
        move more than the product physically holds (computed from the active
        movement lines via ``stock.movement_state``).

        SALE products that are created at sale time (never received into
        stock) are exempt — the sale itself is what records them.  DEATH and
        CONSUMPTION always enforce availability: you cannot write off more
        than the project actually holds.
        """
        if self.reversal_of_id is not None or self.product_id is None:
            return
        from apps.app_operation.models.operation_type import OperationType

        if self._outbound_owner_entity() is None:
            return
        if (
            self.operation.operation_type == OperationType.SALE
            and not self.product.is_physically_moved
        ):
            return
        from apps.app_inventory.stock import movement_state

        available = movement_state(self.product, as_of=self.date)["quantity"]
        if self.quantity > available:
            raise ValidationError(
                _(
                    "Insufficient stock: %(qty)s requested but only %(avail)s "
                    "available for '%(p)s'."
                )
                % {"qty": self.quantity, "avail": available, "p": self.product}
            )

    def clean(self):
        """Validate cross-field integrity."""
        # Ensure the invoice item belongs to the same operation
        # (skip check when operation is not yet assigned, e.g. during form
        #  validation before the view sets line.operation)
        if (
            self.operation_id is not None
            and self.invoice_item.operation_id != self.operation_id
        ):
            raise ValidationError(_("Invoice item does not belong to this operation."))

        # Prevent over-delivery (skip for reversal lines).
        # Direction-aware: only movements of the same owner count, so an
        # internal-client sale's buyer receipt does not consume the seller's
        # invoice-item budget.
        if self.reversal_of_id is None:
            already_moved_qs = InventoryMovementLine.objects.filter(
                invoice_item=self.invoice_item,
                reversal_of__isnull=True,
            )
            # Originals that have since been reversed no longer count as moved.
            reversed_originals = InventoryMovementLine.objects.filter(
                invoice_item=self.invoice_item, reversal_of__isnull=False
            ).values_list("reversal_of_id", flat=True)
            already_moved_qs = already_moved_qs.exclude(
                id__in=list(reversed_originals)
            )
            if self.product_id is not None:
                already_moved_qs = already_moved_qs.filter(
                    product__entity=self.product.entity
                )
            already_moved = (
                already_moved_qs.exclude(pk=self.pk).aggregate(total=Sum("quantity"))[
                    "total"
                ]
                or Decimal("0")
            )
            if already_moved + self.quantity > self.invoice_item.quantity:
                raise ValidationError(
                    _(
                        "Total moved quantity (%(moved)s) would exceed the invoice "
                        "item quantity (%(max)s)."
                    )
                    % {
                        "moved": already_moved + self.quantity,
                        "max": self.invoice_item.quantity,
                    }
                )

        # Validate the product can be moved (SOLD/DEAD allowed for reversals)
        # (skip when product is not yet assigned, e.g. during form validation)
        if self.product_id is not None:
            from apps.app_operation.models.operation_type import OperationType

            # Ownership: for outbound operations the moved product must belong
            # to the entity whose inventory it leaves. Prevents moving another
            # project's stock out of this project. Reversal lines are exempt
            # (they restore stock to its original location).
            if self.reversal_of_id is None:
                owner = self._outbound_owner_entity()
                if owner is not None and self.product.entity_id != owner.id:
                    raise ValidationError(
                        _(
                            "Product '%(p)s' does not belong to '%(entity)s' and "
                            "cannot be moved out of it."
                        )
                        % {"p": self.product, "entity": owner}
                    )
                # Availability: never move more than the product physically holds.
                self._validate_availability()
                # Unit consistency: quantity must be a positive multiple of the
                # template's minimum increment (e.g. 1 for Head, 0.01 for Kg).
                min_qty = self.product.product_template.minimum_quantity
                if min_qty and min_qty > 0 and (self.quantity % min_qty) != 0:
                    raise ValidationError(
                        _(
                            "Quantity %(qty)s must be a multiple of the minimum "
                            "increment %(min)s for '%(p)s'."
                        )
                        % {"qty": self.quantity, "min": min_qty, "p": self.product}
                    )

            # Movement lines ARE the physical move, so obligated-only products
            # (registered but not yet moved) are allowed here. For terminal
            # operations (SALE/DEATH/CONSUMPTION) the moved product legitimately
            # carries the matching terminal status (SOLD/DEAD/CONSUMED), so it
            # must be allowed too.
            terminal_status_by_op = {
                OperationType.SALE: Product.Status.SOLD,
                OperationType.DEATH: Product.Status.DEAD,
                OperationType.CONSUMPTION: Product.Status.CONSUMED,
            }
            op_type = self.operation.operation_type
            if op_type in (OperationType.PURCHASE, OperationType.BIRTH):
                # Inbound receipt (PURCHASE/BIRTH) brings the purchased/born lot
                # INTO stock, so the lot's own current status (e.g. SOLD after a
                # partial dispatch) must never block receiving the remaining
                # quantity. The purchase created the Product instance and the
                # movement only materialises it further — receiving the rest of
                # a lot that was partially sold re-activates it.
                allow_status = True
            else:
                allow_status = (
                    self.product.status == terminal_status_by_op.get(op_type)
                )
            self.product.validate_active(
                allow_reversal=self.reversal_of_id is not None,
                allow_obligated=True,
                allow_adjustment=allow_status,
            )

        super().clean()

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        # Lazy-create Product if not provided (e.g. purchase flow where the
        # caller passes product=None expecting save() to materialise it from
        # the invoice_item's product_template).
        #
        # ``_lazy_unique_id`` (a transient, non-model attribute) lets the caller
        # forward the user-edited tag through to the created product; when
        # absent, create_products_for_item() auto-generates one for INDIVIDUAL
        # templates.
        #
        # ``_lazy_gender`` / ``_lazy_birth_date`` / ``_lazy_mother`` are set by
        # the birth flow so a lazily-created newborn carries its sex, birth date
        # and mother link.
        if is_new and self.product_id is None and self.invoice_item_id is not None:
            # The owning entity is the project — for PURCHASE that is the source,
            # for BIRTH the destination (its source is the System entity).
            receiving_entity = self.operation.inventory_receiving_entity
            products = InvoiceItem.create_products_for_item(
                invoice_item=self.invoice_item,
                entity=receiving_entity or self.operation.source,
                quantity=self.quantity,
                unit_price=self.invoice_item.unit_price,
                unique_id=getattr(self, "_lazy_unique_id", None) or None,
                gender=getattr(self, "_lazy_gender", None),
                birth_date=getattr(self, "_lazy_birth_date", None),
                mother=getattr(self, "_lazy_mother", None),
            )
            self.product = products[0]
        super().save(*args, **kwargs)

    def reverse(self, officer, date=None, group_key=None):
        """
        Create a reversal line that negates this one.  Stock queries exclude
        reversal lines (and the originals they reverse).
        """
        if InventoryMovementLine.objects.filter(reversal_of=self).exists():
            raise ValidationError(
                _("Movement line %(pk)s has already been reversed.") % {"pk": self.pk}
            )
        return InventoryMovementLine.objects.create(
            operation=self.operation,
            invoice_item=self.invoice_item,
            product=self.product,
            quantity=self.quantity,
            date=date or today_date.today(),
            notes=_("Reversal of movement line %(pk)s") % {"pk": self.pk},
            reversal_of=self,
            group_key=group_key or "",
            officer=officer,
        )

    @classmethod
    def batch_reverse(cls, lines, officer, date=None):
        """
        Reverse every line in the *lines* queryset.

        Returns the list of newly created reversal lines.
        """
        created = []
        for line in lines:
            if not cls.objects.filter(reversal_of=line).exists():
                created.append(
                    line.reverse(officer=officer, date=date, group_key="batch")
                )
        return created

    def __str__(self):
        return (
            f"MovementLine {self.pk} — {self.invoice_item} "
            f"qty={self.quantity} op={self.operation_id}"
        )

    class Meta:
        verbose_name = _("inventory movement line")
        verbose_name_plural = _("inventory movement lines")
        ordering = ["-date", "-created_at"]
