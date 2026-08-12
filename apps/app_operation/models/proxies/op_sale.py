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

        The wizard selects the seller's **existing** products from stock; this
        factory links them to the SALE ``InvoiceItem``(s) and records
        ``SALE_MOVEMENT`` lines that affect them (the sold product leaves the
        seller's stock, status → SOLD). No new products are minted.

        Orchestrates the full creation pipeline inside a single transaction:
          1. Integrity check (item totals vs declared total)
          2. ``SaleOperation`` record
          3. ``InvoiceItem`` per session item (template from the selected product)
          4. Availability + ownership validation on the selected product
          5. ``InventoryMovementLine`` (SALE_MOVEMENT) against the selected
             product + link it to the invoice item
          6. Payment transaction (if ``amount_paid > 0``)

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

        # ── 3. Resolve the seller's existing products & record movements ──
        group_key = uuid.uuid4().hex[:8]

        # Concurrency: lock the products being sold so concurrent sales on the
        # same stock serialize (SELECT ... FOR UPDATE; no-op on SQLite).
        Product.lock_ids([int(item_data["product_id"]) for item_data in items_data])

        for item_data in items_data:
            # The selected product already exists in the project's stock — the
            # sale AFFECTS it (SALE_MOVEMENT), it is never minted here.
            product = Product.objects.filter(
                pk=item_data["product_id"], entity=project
            ).first()
            if product is None:
                raise ValidationError(
                    _("Selected product not found or does not belong to this project.")
                )
            product.validate_active()

            qty = Decimal(item_data["quantity"])
            unit_price = Decimal(item_data["unit_price"])

            # Availability: cannot sell more than the physically-present on-hand.
            from apps.app_inventory.stock import movement_state

            available = movement_state(product, as_of=date_val)["quantity"]
            if qty > available:
                raise ValidationError(
                    _(
                        "Insufficient stock: %(qty)s requested but only %(avail)s "
                        "available for '%(p)s'."
                    )
                    % {"qty": qty, "avail": available, "p": product}
                )

            # ── 4. InvoiceItem (from the selected product's template) ───
            invoice_item = InvoiceItem.objects.create(
                operation=op,
                product_template=product.product_template,
                description=item_data.get("description", ""),
                quantity=qty,
                unit_price=unit_price,
            )

            # ── 5. Link the sold product + record the outbound movement ──
            #      The product leaves the seller's stock (status → SOLD via the
            #      linked SALE item); SALE_MOVEMENT writes the ledger row.
            product.invoice_items.add(invoice_item)
            InventoryMovementLine.objects.create(
                operation=op,
                invoice_item=invoice_item,
                product=product,
                quantity=qty,
                date=date_val,
                officer=officer,
                notes="",
                group_key=group_key,
            )

            # ── 5b. Internal client: the buyer receives the goods ─────────
            #      The sale preselects the product, so the exact template,
            #      quantity and price are known. Create the buyer's copy owned
            #      by the client (direction-aware status → ACTIVE) and record
            #      its receipt (inbound movement, direction-aware ledger).
            if client.is_internal:
                buyer_products = InvoiceItem.create_products_for_item(
                    invoice_item=invoice_item,
                    entity=client,
                    quantity=qty,
                    unit_price=unit_price,
                )
                per_product_qty = (
                    Decimal("1") if len(buyer_products) > 1 else qty
                )
                for buyer_product in buyer_products:
                    InventoryMovementLine.objects.create(
                        operation=op,
                        invoice_item=invoice_item,
                        product=buyer_product,
                        quantity=per_product_qty,
                        date=date_val,
                        officer=officer,
                        notes="",
                        group_key=group_key,
                    )

        # ── 6. Payment processing (shared base method) ─────────────────
        if paid > Decimal("0"):
            op.process_payment(
                amount_paid=paid,
                officer=officer,
                date=date_val,
                description=_("Payment for Sale #%(pk)s") % {"pk": op.pk},
            )

        return op
