"""Purchase-operation proxy.

:class:`PurchaseOperation` records stock bought from a vendor: it validates the
invoice items, applies the receive movements into inventory, and settles the
vendor through the purchase payment.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from apps.app_operation.models.operation import AdjustableTransactionMixin, Operation
from apps.app_transaction.transaction_type import TransactionType


class PurchaseOperation(AdjustableTransactionMixin, Operation):
    """Concrete operation proxy for a purchase.

    Records stock bought from a vendor: it validates the invoice items, receives
    the items into inventory and settles the vendor through the purchase payment.
    """

    _issuance_transaction_type = TransactionType.PURCHASE_ISSUANCE
    _payment_transaction_type = TransactionType.PURCHASE_PAYMENT

    url_str = "purchase"
    label = "Purchase Issuance"
    _source_role = "url"
    _dest_role = "post"
    can_pay = True
    # Balance check required: the project fund is the real payer. Issuance can succeed
    # with insufficient balance; each individual payment is guarded at settlement time.
    check_balance_on_payment = True
    is_partially_payable = True
    has_category = False
    has_invoice = True
    _is_one_shot_operation = False
    has_repayment = False
    max_payment_transaction_count = -1
    creates_assets = True

    is_adjustable = True

    class Meta:
        proxy = True
        verbose_name = "Purchase"

    @property
    def payment_source_fund(self):
        """The project fund paying for the purchase."""
        return self.source  # clean_source ensures this is a project (pays)

    @property
    def payment_target_fund(self):
        """The vendor fund receiving the purchase payment."""
        return self.destination  # clean_destination ensures this is a vendor (receives)

    @property
    def project(self):
        """The project buying the stock (the source entity)."""
        return self.source

    @property
    def vendor(self):
        """The vendor selling the stock."""
        return self.destination

    def clean_source(self):
        """Require the purchase source to be a Project entity."""
        if not self.source.is_project:
            raise ValidationError("Purchase source must be a Project entity.")

    @classmethod
    def get_related_entities(cls, url_entity, config):
        """External entities registered as active vendors of the project.

        The World entity is always offered as an ad-hoc vendor (no Stakeholder
        record required), so the user can register a one-off purchase against an
        entity that is not worth creating in the database.
        """
        from apps.app_entity.models import (
            Entity,
            EntityType,
            Stakeholder,
            StakeholderRole,
        )

        # Internal entities cannot be vendors — purchases are external-only.
        relationships = (
            Stakeholder.objects.filter(
                parent=url_entity, role=StakeholderRole.VENDOR, active=True
            )
            .exclude(target__is_internal=True)
            .select_related("target")
            .all()
        )
        related = [s.target for s in relationships]
        world = Entity.objects.filter(entity_type=EntityType.WORLD).first()
        if world is not None and world not in related:
            related.append(world)
        return related

    def clean_destination(self):
        """Require an active, non-internal vendor of the source project.

        The World entity is allowed without a Stakeholder record (ad-hoc
        purchase). All other destinations keep the strict vendor + Stakeholder
        validation.
        """
        if self.destination.is_world:
            return
        if not self.destination.is_vendor:
            raise ValidationError("Purchase destination must be a Vendor entity.")
        # Internal entities cannot be vendors — purchases are external-only and
        # intra-farm stock transfers happen through a SALE.
        if self.destination.is_internal:
            raise ValidationError(
                "Internal entities cannot be vendors to each other. To transfer goods between "
                "internal entities, record a sale from the other side."
            )
        from apps.app_entity.models import Stakeholder, StakeholderRole

        if not Stakeholder.objects.filter(
            parent=self.source,
            target=self.destination,
            role=StakeholderRole.VENDOR,
            active=True,
        ).exists():
            raise ValidationError(
                "Purchase destination must be an active vendor of the source project."
            )

    @property
    def _implicit_reversable_transaction_types(self):
        """Payment is reversed implicitly for a World purchase.

        A World purchase is fully paid at creation and its payment can never be
        reversed on its own, so operation-level reversal must reverse both the
        issuance and the payment together.
        """
        types = list(super()._implicit_reversable_transaction_types)
        payment = getattr(self, "_payment_transaction_type", None)
        if self.destination.is_world and payment is not None:
            types.append(payment)
        return types

    # ------------------------------------------------------------------
    # Factory — consolidate wizard submit logic
    # ------------------------------------------------------------------

    @classmethod
    @transaction.atomic
    def create_from_session(
        cls, project, session_data: dict, officer
    ) -> "PurchaseOperation":
        """
        Create a fully-formed PurchaseOperation from wizard session data.

        Orchestrates the full creation pipeline inside a single transaction:
          1. Integrity check (item totals vs declared total)
          2. ``PurchaseOperation`` record
          3. ``InvoiceItem`` per session item
          4. ``InventoryMovementLine`` for any received quantities
             (products are created **lazily** by the movement line's save())
          5. Payment transaction (if ``amount_paid > 0``)

        Uses shared base class methods for item validation, InvoiceItem
        creation, and payment processing.

        Returns the created ``PurchaseOperation``.

        Raises ``ValidationError`` (or ``ValueError`` for amount mismatch) on
        any integrity failure — the caller is responsible for catching and
        presenting the error.
        """
        from apps.app_inventory.models import InventoryMovementLine

        date_val = datetime.fromisoformat(session_data["date"]).date()
        vendor = cls._resolve_counterparty(
            session_data, "vendor_id", _("Vendor")
        )

        desc = session_data.get("description", "")
        total = Decimal(session_data["total_amount"])
        paid = Decimal(session_data.get("amount_paid", "0"))
        items_data = session_data["items"]

        # ── 0. World purchases must be fully paid at creation ──────────
        if vendor.is_world and paid != total:
            raise ValidationError(
                _("A purchase from the World must be paid in full at creation.")
            )

        # ── 1. Integrity check (shared base method) ────────────────────
        cls._validate_item_totals(items_data, total)

        # ── 2. Create operation ────────────────────────────────────────
        op = cls(
            source=project,
            destination=vendor,
            amount=total,
            date=date_val,
            description=desc,
            officer=officer,
            operation_type="PURCHASE",
        )
        op.save()

        # ── 3. Create InvoiceItems (shared base method) ────────────────
        invoice_items = cls._build_invoice_items(op, items_data)

        # ── 4. InventoryMovementLine(s) for any received quantities ────
        #      INDIVIDUAL → one line per head (qty=1 each); each line's
        #      lazy-create materialises its own tagged Product, so buying 10
        #      heads creates 10 individual Products (one per animal).
        #      COMMODITY  → one line with the full quantity.
        group_key = uuid.uuid4().hex[:8]
        for item_data, invoice_item in zip(items_data, invoice_items):
            received_qty = Decimal(item_data.get("received_qty", "0"))
            if received_qty <= Decimal("0"):
                continue
            uid = (item_data.get("unique_id") or "").strip() or None
            InventoryMovementLine.create_received_movement_lines(
                operation=op,
                invoice_item=invoice_item,
                quantity=received_qty,
                date=date_val,
                officer=officer,
                group_key=group_key,
                lazy_unique_id=uid,
            )

        # ── 5. Payment processing (shared base method) ─────────────────
        if paid > Decimal("0"):
            op.process_payment(
                amount_paid=paid,
                officer=officer,
                date=date_val,
                description=_("Payment for Purchase #%(pk)s") % {"pk": op.pk},
            )

        return op
