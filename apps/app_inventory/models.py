from datetime import date as today_date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.utils.translation import gettext_lazy as _

from apps.app_base.mixins import AmountCleanMixin, ImmutableMixin, OfficerMixin
from apps.app_base.models import BaseModel


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
        PURCHASE = "PURCHASE", _("Purchase")
        SALE = "SALE", _("Sale")
        BIRTH = "BIRTH", _("Birth")
        DEATH = "DEATH", _("Death")
        CONSUMPTION = "CONSUMPTION", _("Consumption")
        CAPITAL_GAIN = "CAPITAL_GAIN", _("Capital Gain")
        CAPITAL_LOSS = "CAPITAL_LOSS", _("Capital Loss")
        REVERSAL = "REVERSAL", _("Reversal")
        ADJUSTMENT = "ADJUSTMENT", _("Adjustment")

    product = models.ForeignKey(
        "Product",
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        verbose_name=_("product"),
    )
    entry_type = models.CharField(
        _("entry type"), max_length=20, choices=EntryType.choices
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
    def record(cls, operation, negate: bool = False) -> tuple[int, int]:
        """
        Write ledger entries for every product linked to *operation*.

        Must be called inside a ``db_transaction.atomic()`` block, **after**
        all InvoiceItems and their Product M2M links are fully committed.

        ``negate=True`` flips the signs and marks entries as REVERSAL — use
        this when recording the cancellation of a previously recorded operation
        (e.g. after ``operation.reverse()``).

        Returns ``(created, skipped)`` counts.
        """
        from apps.app_operation.models.operation_type import OperationType

        _MAP = {
            OperationType.PURCHASE: (cls.EntryType.PURCHASE, 1, 1),
            OperationType.SALE: (cls.EntryType.SALE, -1, -1),
            OperationType.BIRTH: (cls.EntryType.BIRTH, 1, 1),
            OperationType.DEATH: (cls.EntryType.DEATH, -1, -1),
            OperationType.CONSUMPTION: (cls.EntryType.CONSUMPTION, -1, -1),
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

        for item in operation.items.prefetch_related("products").all():
            for product in item.products.all():
                key = f"{key_prefix}item_{item.pk}_product_{product.pk}"
                _, created = cls.objects.get_or_create(
                    idempotency_key=key,
                    defaults={
                        "product": product,
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

        Sign convention mirrors the original operation:
          PURCHASE: qty_sign=+1, val_sign=+1  (positive = inventory gained)
          SALE:     qty_sign=-1, val_sign=-1  (negative = inventory exited)

        ``negate=True`` flips the signs — used when reversing the parent
        InvoiceItemAdjustment.

        Idempotency keys:
          forward:  "adj_line_{line.pk}_product_{product.pk}"
          reversal: "rev_adj_line_{line.pk}_product_{product.pk}"

        Returns ``(created, skipped)`` counts.  Skips if both deltas are zero.
        """
        from apps.app_operation.models.operation_type import OperationType

        qty_delta = line.quantity_delta
        val_delta = line.value_delta

        if qty_delta == 0 and val_delta == 0:
            return 0, 0

        op_type = line.adjustment.operation.operation_type
        if op_type == OperationType.PURCHASE:
            qty_sign, val_sign = 1, 1
        elif op_type == OperationType.SALE:
            qty_sign, val_sign = -1, -1
        else:
            return 0, 0

        if negate:
            qty_sign = -qty_sign
            val_sign = -val_sign

        key_prefix = "rev_" if negate else ""
        date = line.adjustment.date
        entry_type = cls.EntryType.ADJUSTMENT

        # Record against every product linked to the invoice item
        created_count = skipped_count = 0
        for product in line.invoice_item.products.all():
            key = f"{key_prefix}adj_line_{line.pk}_product_{product.pk}"
            _, created = cls.objects.get_or_create(
                idempotency_key=key,
                defaults={
                    "product": product,
                    "entry_type": entry_type,
                    "date": date,
                    "quantity_delta": (qty_delta * qty_sign).quantize(Decimal("0.01")),
                    "value_delta": (val_delta * val_sign).quantize(Decimal("0.01")),
                },
            )
            if created:
                created_count += 1
            else:
                skipped_count += 1

        return created_count, skipped_count

    @classmethod
    def record_movement_line(cls, line, negate: bool = False) -> tuple[int, int]:
        """
        Write ledger entries for one InventoryMovementLine.

        Direction is implicit from the parent operation type:
          PURCHASE → qty_sign=+1, val_sign=+1, entry_type=PURCHASE
          SALE     → qty_sign=-1, val_sign=-1, entry_type=SALE
          negate=True flips the signs and marks entry_type as REVERSAL.

        Idempotency keys use the *original* line pk so a line can only be
        reversed once:
          forward : "movement_line_{line.pk}_product_{product.pk}"
          reversal: "rev_movement_line_{line.reversal_of_id}_product_{product.pk}"

        Value = line.quantity × invoice_item.unit_price (proportional slice).
        """
        from apps.app_operation.models.operation_type import OperationType

        op_type = line.movement.operation.operation_type
        if op_type == OperationType.PURCHASE:
            qty_sign, val_sign = 1, 1
            entry_type = cls.EntryType.PURCHASE
        elif op_type == OperationType.SALE:
            qty_sign, val_sign = -1, -1
            entry_type = cls.EntryType.SALE
        else:
            return 0, 0

        if negate:
            qty_sign = -qty_sign
            val_sign = -val_sign
            entry_type = cls.EntryType.REVERSAL

        source_pk = line.reversal_of_id if negate else line.pk
        key_prefix = "rev_" if negate else ""
        date = line.movement.date
        item = line.invoice_item

        created_count = skipped_count = 0
        for product in item.products.all():
            key = f"{key_prefix}movement_line_{source_pk}_product_{product.pk}"
            _, created = cls.objects.get_or_create(
                idempotency_key=key,
                defaults={
                    "product": product,
                    "entry_type": entry_type,
                    "date": date,
                    "quantity_delta": (line.quantity * qty_sign).quantize(
                        Decimal("0.01")
                    ),
                    "value_delta": (
                        line.quantity * item.unit_price * val_sign
                    ).quantize(Decimal("0.01")),
                },
            )
            if created:
                created_count += 1
            else:
                skipped_count += 1

        return created_count, skipped_count

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    @classmethod
    def state_as_of(cls, product, as_of) -> dict:
        """Return {"quantity": ..., "value": ...} for *product* up to *as_of*."""
        result = cls.objects.filter(product=product, date__lte=as_of).aggregate(
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
        """
        return (
            cls.objects.filter(
                product__product_template__entities=entity, date__lte=as_of
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
    def pending_deliveries(cls, entity=None, as_of=None):
        """
        Return InvoiceItems from PURCHASE operations where the delivered quantity
        is less than the ordered quantity (not yet fully delivered).

        Optionally filter by entity and/or cutoff date.
        Returns a queryset of dicts with ``invoice_item_id``, ``ordered_qty``,
        ``delivered_qty``, ``pending_qty``.
        """
        from apps.app_operation.models.operation_type import OperationType
        from django.db.models.functions import Coalesce

        query = (
            InvoiceItem.objects
            .filter(operation__operation_type=OperationType.PURCHASE)
            .annotate(
                delivered_qty=Coalesce(
                    Sum("movement_lines__quantity", filter=Q(movement_lines__reversal_of__isnull=True)),
                    Decimal("0.00")
                )
            )
            .annotate(
                pending_qty=ExpressionWrapper(
                    F("quantity") - F("delivered_qty"),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            )
            .filter(pending_qty__gt=0)
        )

        if entity:
            query = query.filter(operation__entity=entity)

        if as_of:
            query = query.filter(operation__date__lte=as_of)

        return query.values(
            "id",
            "quantity",
            "delivered_qty",
            "pending_qty",
            "product__name",
            "operation__id",
        ).order_by("operation__date")

    class Meta:
        verbose_name = _("product ledger entry")
        verbose_name_plural = _("product ledger entries")
        indexes = [
            models.Index(fields=["product", "date"]),
        ]


class ProductTemplate(BaseModel):
    class TrackingMode(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", _("Individual (Tag ID)")
        BATCH = "BATCH", _("Batch/Group")
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
    requires_individual_tag = models.BooleanField(
        _("requires individual tag"), default=False
    )

    tracking_mode = models.CharField(
        _("tracking mode"),
        choices=TrackingMode.choices,
        max_length=24,
        default=TrackingMode.BATCH,
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
        return op_type in self._ALLOWED_OP_TYPES.get(self.nature, frozenset())

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
            "requires_individual_tag",
        )


class InvoiceItem(AmountCleanMixin, BaseModel):
    _amount_name = "quantity"

    operation = models.ForeignKey(
        "app_operation.Operation",
        related_name="items",
        on_delete=models.CASCADE,
        verbose_name=_("operation"),
    )
    product = models.ForeignKey(
        ProductTemplate,
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name=_("product"),
    )
    description = models.TextField(_("description"), blank=True)
    quantity = models.DecimalField(
        _("quantity"), max_digits=10, decimal_places=2, default=1
    )
    unit_price = models.DecimalField(_("unit price"), max_digits=15, decimal_places=2)

    @property
    def total_price(self):
        return self.quantity * self.unit_price

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
        if not self.product.accepts_operation(op_type):
            raise ValidationError(
                _(
                    "'%(product)s' (%(nature)s) cannot be used in a %(op_type)s operation."
                )
                % {
                    "product": self.product.name,
                    "nature": self.product.get_nature_display(),
                    "op_type": op_type,
                }
            )
        return super().clean()

    class Meta:
        verbose_name = _("invoice item")
        verbose_name_plural = _("invoice items")


class Product(AmountCleanMixin, BaseModel):
    _amount_name = "unit_price"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Active")
        SOLD = "SOLD", _("Sold")
        DEAD = "DEAD", _("Dead")

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

    @property
    def status(self) -> str:
        from apps.app_operation.models.operation_type import OperationType

        STATUS_CHANGING_TYPES = {
            OperationType.PURCHASE,
            OperationType.BIRTH,
            OperationType.DEATH,
            OperationType.SALE,
        }
        TYPE_TO_STATUS = {
            OperationType.PURCHASE: self.Status.ACTIVE,
            OperationType.BIRTH: self.Status.ACTIVE,
            OperationType.DEATH: self.Status.DEAD,
            OperationType.SALE: self.Status.SOLD,
        }

        last_op = (
            self.invoice_items.filter(
                operation__operation_type__in=STATUS_CHANGING_TYPES
            )
            .order_by("-operation__date", "-operation__created_at")
            .values_list("operation__operation_type", flat=True)
            .first()
        )

        if last_op is None:
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
        self, allow_reversal: bool = False, allow_adjustment: bool = False
    ) -> None:
        """
        Raise ValidationError if product can't participate in operations.
        SOLD/DEAD products are forbidden in normal operations, but allowed in:
        - Reversals (allow_reversal=True): undoing a sale or death
        - Adjustments (allow_adjustment=True): correcting records
        - Movement lines: implicitly allowed if parent operation allows it
        """
        status = self.status
        if status not in (self.Status.SOLD, self.Status.DEAD):
            return

        if allow_reversal or allow_adjustment:
            return

        raise ValidationError(
            _(
                "Product '%(id)s' has status %(status)s and cannot be used in new operations."
            )
            % {"id": self.unique_id or self.pk, "status": status}
        )

    def clean(self) -> None:
        super().clean()  # AmountCleanMixin: unit_price > 0
        # M2M is unavailable until the object has been persisted.
        if self.pk is None:
            return
        for item in self.invoice_items.select_related("operation").all():
            op_type = item.operation.operation_type
            if not self.product_template.accepts_operation(op_type):
                raise ValidationError(
                    _("Product '%(p)s' is not compatible with operation type %(op)s.")
                    % {"p": self.product_template.name, "op": op_type}
                )

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")


class InventoryMovement(ImmutableMixin, OfficerMixin, BaseModel):
    """
    Header record for a physical delivery or dispatch batch.
    Linked to a PURCHASE or SALE operation.  Financial obligations are
    recorded on the operation; this model tracks only the physical movement.
    """

    _immutable_fields = {"operation": {}}

    operation = models.ForeignKey(
        "app_operation.Operation",
        on_delete=models.PROTECT,
        related_name="inventory_movements",
        verbose_name=_("operation"),
    )
    date = models.DateField(_("date"), default=today_date.today)
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventory_movements_supervised",
        verbose_name=_("officer"),
    )
    notes = models.TextField(_("notes"), blank=True)

    def clean(self):
        from apps.app_operation.models.operation_type import OperationType

        if self.operation.operation_type not in (
            OperationType.PURCHASE,
            OperationType.SALE,
        ):
            raise ValidationError(
                _("InventoryMovement is only allowed for PURCHASE or SALE operations.")
            )
        super().clean()

    def reverse(self, officer, date=None):
        """Reverse every non-yet-reversed line in this movement."""
        reversal_movement = InventoryMovement.objects.create(
            operation=self.operation,
            date=date or today_date.today(),
            officer=officer,
            notes=_("Reversal of movement %(pk)s") % {"pk": self.pk},
        )
        for line in self.lines.all():
            if not InventoryMovementLine.objects.filter(reversal_of=line).exists():
                line.reverse(officer=officer, date=date, movement=reversal_movement)
        return reversal_movement

    def __str__(self):
        return f"InventoryMovement {self.pk} — {self.operation}"

    class Meta:
        verbose_name = _("inventory movement")
        verbose_name_plural = _("inventory movements")
        ordering = ["-date", "-created_at"]


class InventoryMovementLine(ImmutableMixin, BaseModel):
    """
    One line in an InventoryMovement.  Records the quantity of a specific
    InvoiceItem that was physically received or dispatched.

    Direction is implicit from the parent operation type (PURCHASE=inbound,
    SALE=outbound).  Reversal lines are linked via reversal_of; they write
    negating ProductLedgerEntry rows on save.
    """

    _immutable_fields = {"movement": {}, "invoice_item": {}, "quantity": {}}

    movement = models.ForeignKey(
        InventoryMovement,
        on_delete=models.PROTECT,
        related_name="lines",
        verbose_name=_("movement"),
    )
    invoice_item = models.ForeignKey(
        InvoiceItem,
        on_delete=models.PROTECT,
        related_name="movement_lines",
        verbose_name=_("invoice item"),
    )
    quantity = models.DecimalField(
        _("quantity"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    reversal_of = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversed_by",
        verbose_name=_("reversal of"),
    )

    def clean(self):
        if self.invoice_item.operation_id != self.movement.operation_id:
            raise ValidationError(
                _("Invoice item does not belong to this movement's operation.")
            )
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
                        "Total moved quantity (%(moved)s) would exceed the invoice item "
                        "quantity (%(max)s)."
                    )
                    % {
                        "moved": already_moved + self.quantity,
                        "max": self.invoice_item.quantity,
                    }
                )

        # Validate products can be moved (SOLD/DEAD allowed for reversals/returns)
        is_reversal = self.reversal_of_id is not None
        for product in self.invoice_item.products.all():
            product.validate_active(allow_reversal=is_reversal)

        super().clean()

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            negate = self.reversal_of_id is not None
            ProductLedgerEntry.record_movement_line(self, negate=negate)

    def reverse(self, officer, date=None, movement=None):
        """
        Create a reversal line (and its movement header if not supplied).
        Writes negating ProductLedgerEntry rows automatically via save().
        """
        if InventoryMovementLine.objects.filter(reversal_of=self).exists():
            raise ValidationError(
                _("Movement line %(pk)s has already been reversed.") % {"pk": self.pk}
            )
        if movement is None:
            movement = InventoryMovement.objects.create(
                operation=self.movement.operation,
                date=date or today_date.today(),
                officer=officer,
                notes=_("Reversal of movement line %(pk)s") % {"pk": self.pk},
            )
        return InventoryMovementLine.objects.create(
            movement=movement,
            invoice_item=self.invoice_item,
            quantity=self.quantity,
            reversal_of=self,
        )

    def __str__(self):
        return f"MovementLine {self.pk} — {self.invoice_item} qty={self.quantity}"

    class Meta:
        verbose_name = _("inventory movement line")
        verbose_name_plural = _("inventory movement lines")
