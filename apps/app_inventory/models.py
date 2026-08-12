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


# ---------------------------------------------------------------------------
# Inventory valuation
# ---------------------------------------------------------------------------


def valuation_unit_cost(product) -> Decimal:
    """
    Unit cost used to value outbound inventory movements (SALE/DEATH/
    CONSUMPTION).

    Current method: the cost carried on the product (``Product.unit_price``) —
    i.e. the purchase price for products that entered stock via PURCHASE/BIRTH.

    NOTE: other valuation methods (moving average, FIFO) may be added here
    later — see ai-plans/inventory-integrity-fixes-plan.md (Fix 9).
    """
    if product is None:
        return Decimal("0.00")
    return product.unit_price


class ProductLedgerEntry(BaseModel):
    """
    Append-only ledger of inventory events per product.

    Every operation that changes a product's quantity or value appends a row
    here.  Point-in-time state is always:

        SUM(quantity_delta WHERE product=p AND date <= as_of)
        SUM(value_delta   WHERE product=p AND date <= as_of)

    Never update or delete rows — only append.
    Duplicate prevention is enforced by the DB-level unique constraint on
    ``idempotency_key``.  ``get_or_create`` makes every write idempotent.
    """

    class EntryType(models.TextChoices):
        # --- Issuance (contract) ---
        PURCHASE_ISSUANCE = "PURCHASE_ISSUANCE", _("Purchase Issuance")
        SALE_ISSUANCE = "SALE_ISSUANCE", _("Sale Issuance")
        BIRTH_ISSUANCE = "BIRTH_ISSUANCE", _("Birth Issuance")
        DEATH_ISSUANCE = "DEATH_ISSUANCE", _("Death Issuance")
        CONSUMPTION_ISSUANCE = "CONSUMPTION_ISSUANCE", _("Consumption Issuance")

        # --- Movement (physical) ---
        PURCHASE_MOVEMENT = "PURCHASE_MOVEMENT", _("Purchase Movement")
        SALE_MOVEMENT = "SALE_MOVEMENT", _("Sale Movement")
        BIRTH_MOVEMENT = "BIRTH_MOVEMENT", _("Birth Movement")
        DEATH_MOVEMENT = "DEATH_MOVEMENT", _("Death Movement")
        CONSUMPTION_MOVEMENT = "CONSUMPTION_MOVEMENT", _("Consumption Movement")

        # --- Adjustment (contract change) — direction is in the type name ---
        PURCHASE_ADJUSTMENT_INCREASE = "PURCHASE_ADJ_INC", _(
            "Purchase Adjustment Increase"
        )
        PURCHASE_ADJUSTMENT_DECREASE = "PURCHASE_ADJ_DEC", _(
            "Purchase Adjustment Decrease"
        )
        SALE_ADJUSTMENT_INCREASE = "SALE_ADJ_INC", _("Sale Adjustment Increase")
        SALE_ADJUSTMENT_DECREASE = "SALE_ADJ_DEC", _("Sale Adjustment Decrease")

        # --- Value-only (no quantity) ---
        CAPITAL_GAIN = "CAPITAL_GAIN", _("Capital Gain")
        CAPITAL_LOSS = "CAPITAL_LOSS", _("Capital Loss")

        REVERSAL = "REVERSAL", _("Reversal")

    # -- Class constants for query filtering --

    MOVEMENT_TYPES = frozenset(
        [
            "PURCHASE_MOVEMENT",
            "SALE_MOVEMENT",
            "BIRTH_MOVEMENT",
            "DEATH_MOVEMENT",
            "CONSUMPTION_MOVEMENT",
            "CAPITAL_GAIN",
            "CAPITAL_LOSS",
        ]
    )

    _ISSUANCE_TYPES_FOR_PURCHASE = frozenset(
        [
            "PURCHASE_ISSUANCE",
            "PURCHASE_ADJ_INC",
            "PURCHASE_ADJ_DEC",
        ]
    )

    _ISSUANCE_TYPES_FOR_SALE = frozenset(
        [
            "SALE_ISSUANCE",
            "SALE_ADJ_INC",
            "SALE_ADJ_DEC",
        ]
    )

    _MOVEMENT_TYPES_FOR_PURCHASE = frozenset(["PURCHASE_MOVEMENT"])
    _MOVEMENT_TYPES_FOR_SALE = frozenset(["SALE_MOVEMENT"])

    # -- Fields --

    product = models.ForeignKey(
        "Product",
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        verbose_name=_("product"),
        null=True,
        blank=True,
    )
    invoice_item = models.ForeignKey(
        "InvoiceItem",
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        verbose_name=_("invoice item"),
        null=True,
        blank=True,
    )
    entry_type = models.CharField(
        _("entry type"), max_length=30, choices=EntryType.choices
    )
    date = models.DateField(_("date"), db_index=True)
    quantity_delta = models.DecimalField(
        _("quantity delta"), max_digits=10, decimal_places=2
    )
    value_delta = models.DecimalField(_("value delta"), max_digits=15, decimal_places=2)
    # Computed by the caller as  "item_{item.pk}_product_{product.pk}"
    # or "rev_item_{item.pk}_product_{product.pk}" for reversals.
    # DB-level unique constraint prevents duplicate entries.
    idempotency_key = models.CharField(
        _("idempotency key"), max_length=100, unique=True
    )

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    @classmethod
    def record(
        cls, operation, negate: bool = False, product_map: dict | None = None
    ) -> tuple[int, int]:
        """
        Write **issuance** (contract) ledger entries for *operation*.

        One entry per InvoiceItem (not per Product).  For operations where products
        don't exist yet (PURCHASE, SALE, BIRTH), ``product`` is NULL.  Where products
        are known at creation time (DEATH, CONSUMPTION), use *product_map* to link them.

        *product_map* is ``{invoice_item_pk: product}`` — used by ``save_inventory()``
        for DEATH/CONSUMPTION operations.

        ``negate=True`` flips the signs and marks entries as REVERSAL.

        Must be called inside a ``db_transaction.atomic()`` block.

        Returns ``(created, skipped)`` counts.
        """
        from apps.app_operation.models.operation_type import OperationType

        _MAP = {
            OperationType.PURCHASE: (cls.EntryType.PURCHASE_ISSUANCE, 1, 1),
            OperationType.SALE: (cls.EntryType.SALE_ISSUANCE, -1, -1),
            OperationType.BIRTH: (cls.EntryType.BIRTH_ISSUANCE, 1, 1),
            OperationType.DEATH: (cls.EntryType.DEATH_ISSUANCE, -1, -1),
            OperationType.CONSUMPTION: (cls.EntryType.CONSUMPTION_ISSUANCE, -1, -1),
            OperationType.CAPITAL_GAIN: (cls.EntryType.CAPITAL_GAIN, 0, 1),
            OperationType.CAPITAL_LOSS: (cls.EntryType.CAPITAL_LOSS, 0, -1),
        }

        mapping = _MAP.get(operation.operation_type)
        if mapping is None:
            return 0, 0

        entry_type, qty_sign, val_sign = mapping

        if negate:
            qty_sign = -qty_sign
            val_sign = -val_sign
            entry_type = cls.EntryType.REVERSAL

        key_prefix = "rev_" if negate else ""
        date = operation.date
        created_count = skipped_count = 0
        product_map = product_map or {}

        for item in operation.items.all():
            # Determine product: from product_map (DEATH/CONSUMPTION) or None (lazy)
            product = product_map.get(item.pk)
            key = f"{key_prefix}issuance_item_{item.pk}"
            obj, created = cls.objects.get_or_create(
                idempotency_key=key,
                defaults={
                    "product": product,
                    "invoice_item": item,
                    "entry_type": entry_type,
                    "date": date,
                    "quantity_delta": (item.quantity * qty_sign).quantize(
                        Decimal("0.01")
                    ),
                    "value_delta": (item.total_price * val_sign).quantize(
                        Decimal("0.01")
                    ),
                },
            )
            if created:
                created_count += 1
            else:
                skipped_count += 1

        return created_count, skipped_count

    @classmethod
    def record_adjustment_line(cls, line, negate: bool = False) -> tuple[int, int]:
        """
        Write a ledger correction for a single InvoiceItemAdjustmentLine.

        Direction is hardcoded in the entry type:
          PURCHASE_ADJ_INC  = always increases inventory (positive effect)
          PURCHASE_ADJ_DEC  = always decreases inventory (negative effect)
          SALE_ADJ_INC      = always increases inventory (positive effect)
          SALE_ADJ_DEC      = always decreases inventory (negative effect)

        ``negate=True`` flips the signs — used when reversing the parent
        InvoiceItemAdjustment.

        Idempotency keys:
          forward:  "adj_{inc|dec}_line_{line.pk}"
          reversal: "rev_adj_{inc|dec}_line_{line.pk}"

        Returns ``(created, skipped)`` counts.  Skips if both deltas are zero.
        """
        from apps.app_operation.models.operation_type import OperationType

        qty_delta = line.quantity_delta
        val_delta = line.value_delta

        if qty_delta == 0 and val_delta == 0:
            return 0, 0

        op_type = line.adjustment.operation.operation_type

        # Determine whether this change is an increase or decrease
        is_increase = val_delta > 0 or (val_delta == 0 and qty_delta > 0)

        # Map to the correct adjustment type
        _ADJUSTMENT_TYPE_MAP = {
            (OperationType.PURCHASE, True): cls.EntryType.PURCHASE_ADJUSTMENT_INCREASE,
            (OperationType.PURCHASE, False): cls.EntryType.PURCHASE_ADJUSTMENT_DECREASE,
            (OperationType.SALE, True): cls.EntryType.SALE_ADJUSTMENT_INCREASE,
            (OperationType.SALE, False): cls.EntryType.SALE_ADJUSTMENT_DECREASE,
        }

        entry_type = _ADJUSTMENT_TYPE_MAP.get((op_type, is_increase))
        if entry_type is None:
            return 0, 0

        key_prefix = "rev_" if negate else ""
        inc_dec = "inc" if is_increase else "dec"
        date = line.adjustment.date
        item = line.invoice_item

        if negate:
            qty_delta = Decimal(-qty_delta)
            val_delta = Decimal(-val_delta)

        key = f"{key_prefix}adj_{inc_dec}_line_{line.pk}"
        obj, created = cls.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "product": None,
                "invoice_item": item,
                "entry_type": entry_type,
                "date": date,
                "quantity_delta": Decimal(qty_delta).quantize(Decimal("0.01")),
                "value_delta": Decimal(val_delta).quantize(Decimal("0.01")),
            },
        )
        return (1, 0) if created else (0, 1)

    @classmethod
    def record_movement_line(cls, line, negate: bool = False) -> tuple[int, int]:
        """
        Write a ledger entry for one InventoryMovementLine.

        Direction is implicit from the parent operation type, using the
        new movement-specific entry types:
          PURCHASE → qty_sign=+1, val_sign=+1, entry_type=PURCHASE_MOVEMENT
          SALE     → qty_sign=-1, val_sign=-1, entry_type=SALE_MOVEMENT
          BIRTH    → qty_sign=+1, val_sign=+1, entry_type=BIRTH_MOVEMENT
          DEATH    → qty_sign=-1, val_sign=-1, entry_type=DEATH_MOVEMENT
          CONSUMPTION → qty_sign=-1, val_sign=-1, entry_type=CONSUMPTION_MOVEMENT
          negate=True flips the signs and marks entry_type as REVERSAL.

        Idempotency keys use the *original* line pk so a line can only be
        reversed once:
          forward : "movement_line_{line.pk}_product_{line.product_id}"
          reversal: "rev_movement_line_{line.reversal_of_id}_product_{line.product_id}"

        Value = line.quantity × invoice_item.unit_price (proportional slice).
        """
        from apps.app_operation.models.operation_type import OperationType

        op_type = line.operation.operation_type
        _MOVEMENT_TYPE_MAP = {
            OperationType.PURCHASE: (cls.EntryType.PURCHASE_MOVEMENT, 1, 1),
            OperationType.SALE: (cls.EntryType.SALE_MOVEMENT, -1, -1),
            OperationType.BIRTH: (cls.EntryType.BIRTH_MOVEMENT, 1, 1),
            OperationType.DEATH: (cls.EntryType.DEATH_MOVEMENT, -1, -1),
            OperationType.CONSUMPTION: (cls.EntryType.CONSUMPTION_MOVEMENT, -1, -1),
        }

        mapping = _MOVEMENT_TYPE_MAP.get(op_type)
        if mapping is None:
            return 0, 0

        entry_type, qty_sign, val_sign = mapping

        if negate:
            qty_sign = -qty_sign
            val_sign = -val_sign
            entry_type = cls.EntryType.REVERSAL

        source_pk = line.reversal_of_id if negate else line.pk
        key_prefix = "rev_" if negate else ""
        date = line.date
        item = line.invoice_item
        product = line.product

        key = f"{key_prefix}movement_line_{source_pk}_product_{product.pk}"
        obj, created = cls.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "product": product,
                "invoice_item": item,
                "entry_type": entry_type,
                "date": date,
                "quantity_delta": (line.quantity * qty_sign).quantize(Decimal("0.01")),
                # Value = quantity × the carried unit cost (see valuation_unit_cost).
                "value_delta": (
                    line.quantity * valuation_unit_cost(product) * val_sign
                ).quantize(Decimal("0.01")),
            },
        )
        return (1, 0) if created else (0, 1)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    @classmethod
    def state_as_of(cls, product, as_of) -> dict:
        """Return {"quantity": ..., "value": ...} for *product* up to *as_of*."""
        result = cls.objects.filter(
            product=product,
            date__lte=as_of,
            entry_type__in=cls.MOVEMENT_TYPES,
        ).aggregate(
            quantity=Sum("quantity_delta"),
            value=Sum("value_delta"),
        )
        return {
            "quantity": result["quantity"] or Decimal("0.00"),
            "value": result["value"] or Decimal("0.00"),
        }

    @classmethod
    def portfolio_as_of(cls, entity, as_of):
        """
        Return a queryset of dicts — one per product still in stock for *entity*
        as of *as_of*.  Each dict has ``product_id``, ``quantity``, ``value``.

        Only MOVEMENT_TYPES entries are counted — issuance entries track
        contractual obligations, not physical stock.
        """
        return (
            cls.objects.filter(
                product__product_template__entities=entity,
                date__lte=as_of,
                entry_type__in=cls.MOVEMENT_TYPES,
            )
            .values("product_id")
            .annotate(
                quantity=Sum("quantity_delta"),
                value=Sum("value_delta"),
            )
            .filter(quantity__gt=0)
            .order_by("product_id")
        )

    @classmethod
    def inventory_value_at(cls, entity, as_of) -> Decimal:
        """Net book value of inventory for entity as of as_of."""
        result = cls.objects.filter(
            product__product_template__entities=entity,
            date__lte=as_of,
            entry_type__in=cls.MOVEMENT_TYPES,
        ).aggregate(value=Sum("value_delta"))
        return result["value"] or Decimal("0.00")

    @classmethod
    def pending_items(cls, entity=None, as_of=None):
        """
        Return InvoiceItems where the moved quantity differs from the issued
        (contracted) quantity — i.e. not yet fully delivered/received.

        Uses the append-only ledger::

            pending_qty = SUM(issuance_types) - SUM(movement_types)

        for each InvoiceItem.  Positive = inbound pending (purchase/birth),
        negative = outbound pending (sale/death/consumption).

        Optionally filter by entity and/or cutoff date.

        Returns a QuerySet of dicts with:
          ``id``, ``quantity``, ``issued_qty``, ``moved_qty``, ``pending_qty``,
          ``product_template__name``, ``operation__id``, ``operation__date``.
        """
        from django.db.models.functions import Coalesce

        from apps.app_operation.models.operation_type import OperationType

        issuance_types = cls._ISSUANCE_TYPES_FOR_PURCHASE | cls._ISSUANCE_TYPES_FOR_SALE

        issued_qty_filter = Q(ledger_entries__entry_type__in=issuance_types)
        if as_of:
            issued_qty_filter &= Q(ledger_entries__date__lte=as_of)

        query = (
            InvoiceItem.objects.annotate(
                issued_qty=Coalesce(
                    Sum(
                        "ledger_entries__quantity_delta",
                        filter=issued_qty_filter,
                    ),
                    Decimal("0.00"),
                ),
                moved_qty=Coalesce(
                    Sum(
                        "ledger_entries__quantity_delta",
                        filter=Q(
                            ledger_entries__entry_type__in=cls.MOVEMENT_TYPES,
                        ),
                    ),
                    Decimal("0.00"),
                ),
            )
            .annotate(
                pending_qty=ExpressionWrapper(
                    F("issued_qty") - F("moved_qty"),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            )
            .filter(~Q(pending_qty=Decimal("0.00")))
        )

        if entity:
            query = query.filter(
                Q(operation__source=entity) | Q(operation__destination=entity)
            )

        if as_of:
            query = query.filter(operation__date__lte=as_of)

        return query.values(
            "id",
            "quantity",
            "issued_qty",
            "moved_qty",
            "pending_qty",
            "product_template__name",
            "operation__id",
            "operation__date",
        ).order_by("operation__date")

    @classmethod
    def pending_deliveries(cls, entity=None, as_of=None):
        """
        Alias for ``pending_items()`` — returns items with pending inbound
        (purchase/birth) obligations.
        """
        return cls.pending_items(entity=entity, as_of=as_of).filter(pending_qty__gt=0)

    class Meta:
        verbose_name = _("product ledger entry")
        verbose_name_plural = _("product ledger entries")
        indexes = [
            models.Index(fields=["product", "date"]),
            models.Index(fields=["invoice_item", "entry_type"]),
        ]


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
    # Pending-items lookup  (use ProductLedgerEntry.pending_items() instead)
    #
    # Previously had unreceived_purchases() and undelivered_sales() here,
    # but those used .exclude() on movement lines — broken for partial
    # deliveries.  Replaced by ProductLedgerEntry.pending_items().
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

        items = cls.objects.filter(operation=operation).annotate(
            already_moved=Sum(
                "movement_lines__quantity",
                filter=Q(movement_lines__reversal_of__isnull=True),
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
        from apps.app_operation.models.operation_type import OperationType

        STATUS_CHANGING_TYPES = {
            OperationType.PURCHASE,
            OperationType.BIRTH,
            OperationType.DEATH,
            OperationType.SALE,
            OperationType.CONSUMPTION,
        }
        TYPE_TO_STATUS = {
            OperationType.PURCHASE: self.Status.ACTIVE,
            OperationType.BIRTH: self.Status.ACTIVE,
            OperationType.DEATH: self.Status.DEAD,
            OperationType.SALE: self.Status.SOLD,
            OperationType.CONSUMPTION: self.Status.CONSUMED,
        }

        # Reversal-aware: exclude operations that have been reversed (reversed_by
        # set) and reversal clones themselves, so reversing a Death/Sale/
        # Consumption restores the product to its prior status (usually ACTIVE).
        last_op = (
            self.invoice_items.filter(
                operation__operation_type__in=STATUS_CHANGING_TYPES,
                operation__reversed_by__isnull=True,
                operation__reversal_of__isnull=True,
            )
            .order_by("-operation__date", "-operation__created_at")
            .values_list("operation__operation_type", flat=True)
            .first()
        )

        if last_op is None:
            # A product whose only entry into stock was a BIRTH that has since
            # been reversed no longer belongs in stock → REMOVED. Any other
            # non-reversed status-changing operation keeps its precedence (e.g.
            # a born-then-sold animal stays SOLD even if the birth is reversed).
            if self.invoice_items.filter(
                operation__operation_type=OperationType.BIRTH,
                operation__reversed_by__isnull=False,
            ).exists():
                return self.Status.REMOVED
            return self.Status.ACTIVE
        return TYPE_TO_STATUS[last_op]

    @property
    def current_value(self) -> Decimal:
        from apps.app_operation.models.operation_type import OperationType

        base = self.unit_price * self.quantity

        def _sum(op_type):
            result = self.invoice_items.filter(
                operation__operation_type=op_type
            ).aggregate(
                total=Sum(
                    ExpressionWrapper(
                        F("quantity") * F("unit_price"),
                        output_field=DecimalField(max_digits=15, decimal_places=2),
                    )
                )
            )
            return result["total"] or Decimal("0.00")

        return (
            base + _sum(OperationType.CAPITAL_GAIN) - _sum(OperationType.CAPITAL_LOSS)
        )

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
    SALE=outbound).  Reversal lines are linked via ``reversal_of``; they
    write negating ProductLedgerEntry rows on save.

    No longer chained to an ``InventoryMovement`` header — every line carries
    its own ``operation``, ``date``, ``officer`` and ``group_key`` directly.
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
        """
        return self.operation.inventory_owner_entity

    def _validate_availability(self):
        """
        Raise ValidationError if this outbound (non-reversal) movement would
        move more than the product physically holds, per the append-only ledger
        (``ProductLedgerEntry.state_as_of`` counts physical MOVEMENT_TYPES).

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
        available = ProductLedgerEntry.state_as_of(self.product, self.date)[
            "quantity"
        ]
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

        # Prevent over-delivery (skip for reversal lines)
        if self.reversal_of_id is None:
            already_moved = InventoryMovementLine.objects.filter(
                invoice_item=self.invoice_item,
                reversal_of__isnull=True,
            ).exclude(pk=self.pk).aggregate(total=Sum("quantity"))["total"] or Decimal(
                "0"
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
            allow_terminal = (
                self.product.status
                == terminal_status_by_op.get(self.operation.operation_type)
            )
            self.product.validate_active(
                allow_reversal=self.reversal_of_id is not None,
                allow_obligated=True,
                allow_adjustment=allow_terminal,
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
        if is_new:
            negate = self.reversal_of_id is not None
            ProductLedgerEntry.record_movement_line(self, negate=negate)

    def reverse(self, officer, date=None, group_key=None):
        """
        Create a reversal line that negates this one.

        Writes negating ProductLedgerEntry rows automatically via save().
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
