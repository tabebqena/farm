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

        relationships = (
            Stakeholder.objects.filter(
                parent=url_entity, role=StakeholderRole.VENDOR, active=True
            )
            .select_related("target")
            .all()
        )
        return [s.target for s in relationships]

    def clean_destination(self):
        if not self.destination.is_vendor:
            raise ValidationError("Purchase destination must be a Vendor entity.")
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
          4. ``Product``(s) per session item — branching on tracking mode:
             - INDIVIDUAL → N products with quantity=1 each
             - BATCH/COMMODITY → 1 product with quantity=N
             All products are owned by *project* (the purchaser).
          5. ``InventoryMovementLine`` for any received quantities
          6. Payment transaction (if ``amount_paid > 0``)

        Returns the created ``PurchaseOperation``.

        Raises ``ValidationError`` (or ``ValueError`` for amount mismatch) on
        any integrity failure — the caller is responsible for catching and
        presenting the error.
        """
        from apps.app_entity.models import Entity
        from apps.app_inventory.models import (
            InventoryMovementLine,
            InvoiceItem,
            ProductTemplate,
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

        # Integrity check
        computed = sum(
            Decimal(item["quantity"]) * Decimal(item["unit_price"])
            for item in items_data
        )
        if abs(computed - total) > Decimal("0.01"):
            raise ValueError(
                _("Items total %(items)s does not match declared total %(total)s.")
                % {"items": computed, "total": total}
            )

        # 1. Create operation
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

        movement_lines = []

        for item_data in items_data:
            try:
                template = ProductTemplate.objects.get(
                    pk=item_data["product_template_id"]
                )
            except ProductTemplate.DoesNotExist:
                raise ValidationError(
                    _("Product template not found or has been deleted.")
                )

            # 2. Create InvoiceItem
            invoice_item = InvoiceItem.objects.create(
                operation=op,
                product_template=template,
                description=item_data.get("description", ""),
                quantity=Decimal(item_data["quantity"]),
                unit_price=Decimal(item_data["unit_price"]),
            )

            # 3. Create Product(s) — owned by the project (purchaser)
            #    Branching on tracking mode handled by the helper.
            uid = (item_data.get("unique_id") or "").strip() or None
            qty = Decimal(item_data["quantity"])
            unit_price = Decimal(item_data["unit_price"])
            products = InvoiceItem.create_products_for_item(
                invoice_item=invoice_item,
                entity=project,  # ← changed from vendor to project
                quantity=qty,
                unit_price=unit_price,
                unique_id=uid,
            )

            received_qty = Decimal(item_data.get("received_qty", "0"))
            if received_qty > Decimal("0"):
                for product in products:
                    movement_lines.append(
                        (
                            invoice_item,
                            product,
                            (
                                received_qty / len(products)
                                if len(products) > 1
                                else received_qty
                            ),
                        )
                    )

        # 4. InventoryMovementLine records if any received quantities
        if movement_lines:
            group_key = uuid.uuid4().hex[:8]
            for invoice_item, product, received_qty in movement_lines:
                InventoryMovementLine.objects.create(
                    operation=op,
                    invoice_item=invoice_item,
                    product=product,
                    quantity=received_qty,
                    date=date_val,
                    officer=officer,
                    notes="",
                    group_key=group_key,
                )

        # 5. Payment transaction
        if paid > Decimal("0"):
            op.create_payment_transaction(
                amount=paid,
                officer=officer,
                date=date_val,
                description=_("Payment for Purchase #%(pk)s") % {"pk": op.pk},
            )

        return op
