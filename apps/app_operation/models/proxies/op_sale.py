import uuid
from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from apps.app_operation.models.operation import Operation
from apps.app_transaction.transaction_type import TransactionType


class SaleOperation(Operation):
    _issuance_transaction_type = TransactionType.SALE_ISSUANCE
    _payment_transaction_type = TransactionType.SALE_COLLECTION

    url_str = "sale"
    label = "Sale Issuance"
    _source_role = "post"
    _dest_role = "url"
    can_pay = True
    # Balance check required: the client fund is the real payer. Issuance can succeed
    # with insufficient balance; each individual payment is guarded at settlement time.
    check_balance_on_payment = True
    is_partially_payable = True
    has_category = False
    category_required = False
    has_invoice = True
    _is_one_shot_operation = False
    has_repayment = False
    max_payment_transaction_count = -1

    category_type = "SALE"

    is_adjustable = True
    is_items_adjustable = True

    class Meta:
        proxy = True
        verbose_name = "Sale"

    @property
    def payment_source_fund(self):
        return self.source  # clean_source ensures this is a client (pays)

    @property
    def payment_target_fund(self):
        return (
            self.destination
        )  # clean_destination ensures this is a project (collects)

    @property
    def project(self):
        return self.destination

    @property
    def client(self):
        return self.source

    def clean_source(self):
        if not self.source.is_client:
            raise ValidationError("Sale source must be a Client entity.")
        from apps.app_entity.models import Stakeholder, StakeholderRole

        if not Stakeholder.objects.filter(
            parent=self.destination,
            target=self.source,
            role=StakeholderRole.CLIENT,
            active=True,
        ).exists():
            raise ValidationError(
                "Sale source must be an active client of the destination project."
            )

    @classmethod
    def get_related_entities(cls, url_entity, config):
        from apps.app_entity.models import Stakeholder, StakeholderRole

        relationships = (
            Stakeholder.objects.filter(
                parent=url_entity, role=StakeholderRole.CLIENT, active=True
            )
            .select_related("target")
            .all()
        )
        return [s.target for s in relationships]

    def clean_destination(self):
        if not self.destination.is_project:
            raise ValidationError("Sale destination must be a Project entity.")

    # ------------------------------------------------------------------
    # Factory — consolidate wizard submit logic
    # ------------------------------------------------------------------

    @classmethod
    @transaction.atomic
    def create_from_session(
        cls, project, session_data: dict, officer
    ) -> "SaleOperation":
        """
        Create a fully-formed SaleOperation from wizard session data.

        Orchestrates the full creation pipeline inside a single transaction:
          1. Integrity check (item totals vs declared total)
          2. ``SaleOperation`` record
          3. ``InvoiceItem`` per session item
          4. ``Product``(s) for the **project** — branching on tracking mode
             (INDIVIDUAL → N products qty=1; BATCH/COMMODITY → 1 product qty=N).
             The project's product(s) will show status=SOLD via linked operation.
          5. If the **client is internal**, clone product(s) for the client so
             they appear in the client's stock page.
          6. ``InventoryMovementLine`` for any delivered quantities
          7. Payment transaction (if ``amount_paid > 0``)

        Uses shared base class methods for item validation, InvoiceItem
        creation, and payment processing.

        Returns the created ``SaleOperation``.

        Raises ``ValidationError`` (or ``ValueError`` for amount mismatch) on
        any integrity failure — the caller is responsible for catching and
        presenting the error.
        """
        from apps.app_entity.models import Entity
        from apps.app_inventory.models import (
            InventoryMovementLine,
            InvoiceItem,
            Product,
        )

        date_val = datetime.fromisoformat(session_data["date"]).date()
        try:
            client = Entity.objects.get(pk=session_data["client_id"])
        except Entity.DoesNotExist:
            raise ValidationError(_("Client not found or has been deleted."))

        desc = session_data.get("description", "")
        total = Decimal(session_data["total_amount"])
        paid = Decimal(session_data.get("amount_paid", "0"))
        items_data = session_data["items"]

        # ── 1. Integrity check (shared base method) ────────────────────
        cls._validate_item_totals(items_data, total)

        # ── 2. Create operation (source=client, destination=project) ───
        op = cls(
            source=client,
            destination=project,
            amount=total,
            date=date_val,
            description=desc,
            officer=officer,
            operation_type="SALE",
        )
        op.save()

        # ── 3. Create InvoiceItems (shared base method) ────────────────
        invoice_items = cls._build_invoice_items(op, items_data)

        movement_lines = []

        for item_data, invoice_item in zip(items_data, invoice_items):
            # ── 4. Create Product(s) for the project (seller) ──────────
            #      The project's stock decreases; product.status → SOLD via linked op.
            uid = (item_data.get("unique_id") or "").strip() or None
            qty = Decimal(item_data["quantity"])
            unit_price = Decimal(item_data["unit_price"])
            project_products = InvoiceItem.create_products_for_item(
                invoice_item=invoice_item,
                entity=project,
                quantity=qty,
                unit_price=unit_price,
                unique_id=uid,
            )

            # ── 5. If client is internal, clone product(s) for the client ──
            #      so the client can track them in their own stock page.
            #
            #      INTENTIONAL (see ai-plans/inventory-integrity-fixes-plan.md,
            #      Fix 7): the source copy stays SOLD in the seller's stock and
            #      the client copy becomes ACTIVE in the client's stock — the
            #      same physical goods are NOT double-counted as available in
            #      both places, so there is no duplication error. This is the
            #      intra-farm transfer mechanism; a dedicated Stock Transfer
            #      operation is out of scope for now.
            if client.is_internal:
                InvoiceItem.create_products_for_item(
                    invoice_item=invoice_item,
                    entity=client,
                    quantity=qty,
                    unit_price=unit_price,
                    unique_id=uid,
                )

            delivered_qty = Decimal(item_data.get("delivered_qty", "0"))
            if delivered_qty > Decimal("0"):
                for product in project_products:
                    movement_lines.append(
                        (
                            invoice_item,
                            product,
                            (
                                delivered_qty / len(project_products)
                                if len(project_products) > 1
                                else delivered_qty
                            ),
                        )
                    )

        # ── 6. InventoryMovementLine records if any delivered quantities ──
        if movement_lines:
            group_key = uuid.uuid4().hex[:8]
            # Concurrency: lock the products being delivered so concurrent
            # movements on the same stock serialize (SELECT ... FOR UPDATE).
            Product.lock_ids([product.pk for _, product, _ in movement_lines])
            for invoice_item, product, delivered_qty in movement_lines:
                InventoryMovementLine.objects.create(
                    operation=op,
                    invoice_item=invoice_item,
                    product=product,
                    quantity=delivered_qty,
                    date=date_val,
                    officer=officer,
                    notes="",
                    group_key=group_key,
                )

        # ── 7. Payment processing (shared base method) ─────────────────
        if paid > Decimal("0"):
            op.process_payment(
                amount_paid=paid,
                officer=officer,
                date=date_val,
                description=_("Payment for Sale #%(pk)s") % {"pk": op.pk},
            )

        return op
