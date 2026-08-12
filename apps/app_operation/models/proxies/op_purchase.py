import uuid
from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class PurchaseOperation(Operation):
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
    category_required = False
    has_invoice = True
    _is_one_shot_operation = False
    has_repayment = False
    max_payment_transaction_count = -1
    creates_assets = True
    category_type = "PURCHASE"

    is_adjustable = True
    is_items_adjustable = True

    class Meta:
        proxy = True
        verbose_name = "Purchase"

    @property
    def payment_source_fund(self):
        return self.source  # clean_source ensures this is a project (pays)

    @property
    def payment_target_fund(self):
        return self.destination  # clean_destination ensures this is a vendor (receives)

    @property
    def project(self):
        return self.source

    @property
    def vendor(self):
        return self.destination

    def clean_source(self):
        if not self.source.is_project:
            raise ValidationError("Purchase source must be a Project entity.")

    @classmethod
    def get_related_entities(cls, url_entity, config):
        from apps.app_entity.models import Stakeholder, StakeholderRole

        # Internal entities cannot be vendors — purchases are external-only.
        relationships = (
            Stakeholder.objects.filter(
                parent=url_entity, role=StakeholderRole.VENDOR, active=True
            )
            .exclude(target__is_internal=True)
            .select_related("target")
            .all()
        )
        return [s.target for s in relationships]

    def clean_destination(self):
        if not self.destination.is_vendor:
            raise ValidationError("Purchase destination must be a Vendor entity.")
        # Internal entities cannot be vendors — purchases are external-only and
        # intra-farm stock transfers happen through a SALE.
        if self.destination.is_internal:
            raise ValidationError(
                "Internal entities cannot be vendors. To transfer goods between "
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
        from apps.app_entity.models import Entity
        from apps.app_inventory.models import (
            InventoryMovementLine,
        )

        date_val = datetime.fromisoformat(session_data["date"]).date()
        try:
            vendor = Entity.objects.get(pk=session_data["vendor_id"])
        except Entity.DoesNotExist:
            raise ValidationError(_("Vendor not found or has been deleted."))

        desc = session_data.get("description", "")
        total = Decimal(session_data["total_amount"])
        paid = Decimal(session_data.get("amount_paid", "0"))
        items_data = session_data["items"]

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
        from apps.app_inventory.models import ProductTemplate

        group_key = uuid.uuid4().hex[:8]
        for item_data, invoice_item in zip(items_data, invoice_items):
            received_qty = Decimal(item_data.get("received_qty", "0"))
            if received_qty <= Decimal("0"):
                continue
            template = invoice_item.product_template
            uid = (item_data.get("unique_id") or "").strip() or None
            if template.tracking_mode == ProductTemplate.TrackingMode.INDIVIDUAL:
                # One movement line per head — each lazy-creates one tagged
                # Product.  The user-typed tag applies to the first head;
                # the rest auto-generate from the template's tag prefix.
                for head_idx in range(max(int(received_qty), 1)):
                    line = InventoryMovementLine(
                        operation=op,
                        invoice_item=invoice_item,
                        product=None,  # lazy-created by save()
                        quantity=Decimal("1"),
                        date=date_val,
                        officer=officer,
                        notes="",
                        group_key=group_key,
                    )
                    line._lazy_unique_id = uid
                    line.save()
                    uid = None  # subsequent heads auto-generate their tag
            else:
                InventoryMovementLine.objects.create(
                    operation=op,
                    invoice_item=invoice_item,
                    product=None,  # lazy-created by save()
                    quantity=received_qty,
                    date=date_val,
                    officer=officer,
                    notes="",
                    group_key=group_key,
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
