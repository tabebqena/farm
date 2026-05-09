import logging
from datetime import date as today_date
from typing import List

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.app_base.debug import DebugContext
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

logger = logging.getLogger(__name__)

# TODO use database level constrains for data integrity.
# TODO: "Financial Statement" method
# TODO: Integrity check method


class Operation(
    ImmutableMixin,
    AdjustableMixin,
    AmountCleanMixin,
    LinkedIssuanceTransactionMixin,
    LinkedPaymentTransactionMixin,
    LinkedRePaymentTransactionMixin,
    OfficerMixin,
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
    plan = models.ForeignKey(
        "app_operation.FinancialPeriod",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="plan_operations",
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
    category_required: bool = False
    has_repayment: bool = False
    repayment_label: str | None = None
    has_invoice: bool = False
    theme_color: str = "danger"
    theme_icon: str = "bi-box-arrow-up-right"
    creates_assets = False
    category_type = None
    is_adjustable = False
    is_items_adjustable = False

    # ------------------------------------------------------------------
    # Eligibility helpers
    # ------------------------------------------------------------------

    @property
    def can_create_movement(self) -> bool:
        """Whether this operation supports inventory movements."""
        from .operation_type import OperationType

        return self.operation_type in (OperationType.PURCHASE, OperationType.SALE)

    @property
    def can_adjust(self) -> bool:
        """Whether accounting adjustments are allowed on this operation."""
        from .operation_type import OperationType

        return self.operation_type in (
            OperationType.PURCHASE,
            OperationType.SALE,
            OperationType.EXPENSE,
        )

    @property
    def can_item_adjust(self) -> bool:
        """Whether invoice-item adjustments are allowed on this operation."""
        return self.can_create_movement and type(self).has_invoice

    @property
    def can_repay(self) -> bool:
        """Whether this operation supports repayments (e.g. loans, worker advances)."""
        return type(self).has_repayment

    class Meta:
        verbose_name = "Operation"
        verbose_name_plural = "Operations"
        ordering = ["-date", "-created_at"]

    # ------------------------------------------------------------------
    # Request resolution
    # ------------------------------------------------------------------

    @classmethod
    def resolve_request(cls, url_pk, request) -> dict:
        """
        Resolves a request into a unified config + entity dict.
        Call on the proxy class: e.g. PurchaseOperation.resolve_request(pk, request)
        """
        from apps.app_entity.models import Entity, EntityType
        from farm.shortcuts import get_object_or_404

        url_entity = get_object_or_404(
            Entity, pk=url_pk, error_message="Entity not found or has been deleted."
        )
        source_role = cls._source_role
        dest_role = cls._dest_role

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
            "label": cls.label,
            "url_str": cls.url_str,
            "source": source_role,
            "dest": dest_role,
            "can_pay": cls.can_pay,
            "is_partially_payable": cls.is_partially_payable,
            "has_category": cls.has_category,
            "category_required": cls.category_required,
            "has_repayment": cls.has_repayment,
            "has_invoice": cls.has_invoice,
            "repayment_transaction_type": getattr(
                cls, "_repayment_transaction_type", None
            ),
            "theme_color": cls.theme_color,
            "theme_icon": cls.theme_icon,
            "url_entity": url_entity,
            "secondary_entity": secondary_entity,
            "source_entity": resolve(source_role),
            "dest_entity": resolve(dest_role),
        }

    @classmethod
    def get_related_entities(cls, url_entity, config):
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
        rv = []
        if self._issuance_transaction_type:
            rv.append(self._issuance_transaction_type)
        if self._payment_transaction_type:
            rv.append(self._payment_transaction_type)
        return rv

    @property
    def _implicit_reversable_transaction_types(self) -> List[TransactionType]:
        rv = []
        if self._issuance_transaction_type:
            rv.append(self._issuance_transaction_type)
        if self._is_one_shot_operation and self._payment_transaction_type:
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

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        DebugContext.log(
            f"Operation.clean() ({self.operation_type})",
            {
                "is_new": self.pk is None,
                "pk": self.pk,
                "date": str(self.date),
            },
        )
        # Only block NEW, non-reversal operations from landing in a closed period.
        if not self.pk and not getattr(self, "reversal_of_id", None):
            from .period import FinancialPeriod

            # Check both source and destination entities.
            for entity in [self.source, self.destination]:
                if not entity:
                    continue
                closed = FinancialPeriod.objects.filter(
                    entity=entity,
                    end_date__isnull=False,
                    end_date__lt=today_date.today(),  # truly closed: end_date in the past
                    start_date__lte=self.date,
                    end_date__gt=self.date,  # half-open interval: date < end_date
                )
                if closed.exists():
                    DebugContext.error(
                        "Cannot create operation in closed period",
                        data={
                            "date": str(self.date),
                            "entity": str(entity),
                        },
                    )
                    raise ValidationError(
                        "Cannot create an operation whose date falls within a closed financial period."
                    )
        DebugContext.success("Operation validation passed")
        return super().clean()

    def save(self, *args, **kwargs):
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
            DebugContext.log(
                f"Validating {items.count()} invoice items", {"operation_pk": op.pk}
            )
            for item in items:
                item.full_clean()
            DebugContext.success(f"All {items.count()} invoice items validated")

        kwargs.setdefault("post_save_tasks", []).append(
            (
                _validate_invoice_items,
                (self,),
                {},
            )
        )

        with DebugContext.section(
            f"Operation.save() ({self.operation_type})",
            {
                "is_new": is_new,
                "pk": self.pk,
                "source": str(self.source),
                "destination": str(self.destination),
                "amount": float(self.amount),
                "date": str(self.date),
            },
        ):
            result = super().save(*args, **kwargs)
            DebugContext.success("Operation saved", {"pk": self.pk})

            # Audit log the operation
            action = "operation_created" if is_new else "operation_updated"
            DebugContext.audit(
                action=action,
                entity_type="Operation",
                entity_id=self.pk,
                details={
                    "type": self.operation_type,
                    "source": str(self.source),
                    "destination": str(self.destination),
                    "amount": float(self.amount),
                    "date": str(self.date),
                },
                user=str(self.officer),
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

    # ------------------------------------------------------------------
    # Inventory / invoice helpers
    # ------------------------------------------------------------------

    def get_items_data(self):
        """
        Build a list of dicts with movement summaries for each invoice item.
        Used by the detail view to display received/delivered quantities.
        """
        from decimal import Decimal

        from django.db.models import Sum

        from apps.app_inventory.models import InventoryMovementLine

        items = getattr(self, "_cached_items", None)
        items_data = []
        if items is not None:
            for item in items:
                agg = InventoryMovementLine.objects.filter(
                    invoice_item=item,
                    reversal_of__isnull=True,
                ).aggregate(total=Sum("quantity"))
                moved_qty = agg["total"] or Decimal("0.00")
                remaining_qty = item.quantity - moved_qty
                movement_lines = InventoryMovementLine.objects.filter(
                    invoice_item=item,
                    reversal_of__isnull=True,
                ).select_related("product")
                items_data.append(
                    {
                        "item": item,
                        "moved_qty": moved_qty,
                        "remaining_qty": remaining_qty,
                        "is_fully_moved": remaining_qty <= Decimal("0.00"),
                        "movement_lines": movement_lines,
                    }
                )
        return items_data

    def save_inventory(self, bound_formset):
        """
        Called inside an atomic block after the formset is saved.
        - create-mode (PURCHASE/BIRTH): create a Product per item, link via M2M.
        - select-mode (SALE/DEATH/CAPITAL_GAIN/CAPITAL_LOSS): link the chosen Product via M2M.
        Writes ledger entries once all product↔item links are established.
        """
        from apps.app_inventory.models import InvoiceItem, ProductLedgerEntry

        if type(self).creates_assets:
            owning_entity = self.period_entity or self.destination
            for form in bound_formset.forms:
                item = form.instance
                if not item.pk:
                    continue
                uid = form.cleaned_data.get("unique_id", "").strip() or None
                InvoiceItem.create_products_for_item(
                    invoice_item=item,
                    entity=owning_entity,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    unique_id=uid,
                )
        else:
            for form in bound_formset.forms:
                item = form.instance
                if not item.pk:
                    continue
                selected = form.cleaned_data.get("selected_product")
                if selected:
                    is_reversal = getattr(self, "reversal_of_id", None) is not None
                    selected.validate_active(allow_reversal=is_reversal)
                    selected.invoice_items.add(item)

        if self.operation_type not in (OperationType.PURCHASE, OperationType.SALE):
            ProductLedgerEntry.record(self)

    def delete(self, *args, **kwargs):
        """Delete operation with audit logging."""
        with DebugContext.section(
            "Operation.delete()",
            {
                "pk": self.pk,
                "type": self.operation_type,
                "amount": float(self.amount),
            },
        ):
            DebugContext.warn(
                "Deleting operation",
                {
                    "pk": self.pk,
                    "type": self.operation_type,
                    "source": str(self.source),
                    "destination": str(self.destination),
                },
            )

            DebugContext.audit(
                action="operation_deleted",
                entity_type="Operation",
                entity_id=self.pk,
                details={
                    "type": self.operation_type,
                    "amount": float(self.amount),
                },
                user=str(self.officer),
            )

            return super().delete(*args, **kwargs)

    def reverse(self, officer, date=None, reason=None):
        """Reverse an operation with full audit trail."""
        import uuid

        txn_id = f"reverse_op_{self.pk}_{uuid.uuid4().hex[:8]}"
        DebugContext.transaction_start(
            txn_id,
            f"Reversing operation {self.pk}",
            {
                "original_op_pk": self.pk,
                "operation_type": self.operation_type,
                "amount": float(self.amount),
            },
        )

        try:
            reversal = super().reverse(officer=officer, date=date, reason=reason)
            if type(self).has_invoice:
                if self.operation_type in (OperationType.PURCHASE, OperationType.SALE):
                    for movement in self.inventory_movements.prefetch_related(
                        "lines"
                    ).all():
                        movement.reverse(officer=officer, date=date)
                else:
                    from apps.app_inventory.models import ProductLedgerEntry

                    ProductLedgerEntry.record(self, negate=True)

            DebugContext.transaction_commit(
                txn_id,
                {
                    "original_op_pk": self.pk,
                    "reversal_op_pk": reversal.pk,
                    "status": "success",
                },
            )

            DebugContext.audit(
                action="operation_reversed",
                entity_type="Operation",
                entity_id=self.pk,
                details={
                    "type": self.operation_type,
                    "reversal_pk": reversal.pk,
                    "reason": reason or "",
                },
                user=str(officer),
            )

            return reversal
        except Exception as e:
            DebugContext.transaction_rollback(txn_id, str(e), e)
            DebugContext.audit(
                action="operation_reversal_failed",
                entity_type="Operation",
                entity_id=self.pk,
                details={"error": str(e), "reason": reason or ""},
                user=str(officer),
            )
            raise

    def __str__(self):
        return (
            f"Operation {self.operation_type}: "
            f"{self.amount} from {self.source} to {self.destination}"
        )
