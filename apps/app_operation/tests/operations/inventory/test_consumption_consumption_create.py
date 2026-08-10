from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InventoryMovementLine,
    Product,
    ProductLedgerEntry,
    ProductTemplate,
)
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_project_entity,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import ConsumptionOperation, PurchaseOperation
from apps.app_transaction.transaction_type import TransactionType


class ConsumptionCreateTest(TestCase):
    """Consumption creation auto-creates InventoryMovementLine records."""

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = make_user()
        self.project_entity = make_project_entity("Test Farm Project")
        # CONSUMPTION is allowed for FEED/MEDICINE natures only
        self.template = ProductTemplate.objects.create(
            name="Feed Mix",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
        )
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        Stakeholder.objects.create(
            parent=self.project_entity,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )

    def _make_moved_product(self, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Return an ACTIVE, physically-moved product owned by the project.

        A purchase op -> item -> product -> movement line makes the product
        physically present (not obligated-only) and status ACTIVE, so it can
        be selected for a consumption operation.
        """
        purchase = make_operation(
            self.project_entity,
            self.vendor,
            self.officer_user,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=(qty * price).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(purchase, self.template, qty, price)
        product = Product.objects.create(
            product_template=self.template,
            entity=self.project_entity,
            unit_price=price,
            quantity=int(qty),
        )
        product.invoice_items.add(item)
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=qty,
            date=date.today(),
            officer=self.officer_user,
        )
        return product

    def _consume(self, product, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Drive the full ConsumptionOperation.create() pipeline with a formset."""
        raw_post = {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-quantity": str(qty),
            "items-0-unit_price": str(price),
            "items-0-description": "",
            "items-0-selected_product": str(product.pk),
            "items-0-DELETE": "",
        }
        return ConsumptionOperation.create(
            operation_type=OperationType.CONSUMPTION,
            source=self.project_entity,
            destination=self.system_entity,
            amount=(qty * price).quantize(Decimal("0.01")),
            date=date.today(),
            description="Test consumption",
            officer=self.officer_user,
            amount_paid=Decimal("0.00"),
            raw_post=raw_post,
            project=self.project_entity,
        )

    # ------------------------------------------------------------------
    # Movement lines auto-created on create
    # ------------------------------------------------------------------

    def test_create_auto_creates_movement_line(self):
        product = self._make_moved_product()
        op = self._consume(product)

        self.assertIsNotNone(op.pk)
        self.assertEqual(op.movement_lines.count(), 1)

        ml = op.movement_lines.first()
        self.assertEqual(ml.product, product)
        self.assertEqual(ml.quantity, Decimal("5.00"))
        self.assertEqual(ml.invoice_item, op.items.get())
        self.assertEqual(ml.officer, self.officer_user)
        self.assertEqual(ml.date, op.date)
        self.assertTrue(ml.group_key, "Auto-created lines share a group key")
        self.assertIsNone(ml.reversal_of)

    def test_movement_line_uses_the_selected_product(self):
        """The movement line links the exact product chosen in the form, not a
        lazy-created duplicate."""
        product = self._make_moved_product()
        op = self._consume(product)

        ml = op.movement_lines.first()
        self.assertEqual(ml.product.pk, product.pk)
        self.assertEqual(Product.objects.filter(pk=product.pk).count(), 1)

    def test_movement_line_quantity_matches_invoice_item(self):
        product = self._make_moved_product(qty=Decimal("3.00"))
        op = self._consume(product, qty=Decimal("3.00"))

        ml = op.movement_lines.first()
        self.assertEqual(ml.quantity, op.items.get().quantity)

    def test_multiple_items_each_get_a_movement_line_with_shared_group(self):
        product_a = self._make_moved_product()
        product_b = self._make_moved_product()

        op_a = self._consume(product_a)
        op_b = self._consume(product_b)

        # Each operation gets its own movement line
        self.assertEqual(op_a.movement_lines.count(), 1)
        self.assertEqual(op_b.movement_lines.count(), 1)
        self.assertEqual(op_a.movement_lines.first().product, product_a)
        self.assertEqual(op_b.movement_lines.first().product, product_b)

    # ------------------------------------------------------------------
    # Ledger entries
    # ------------------------------------------------------------------

    def test_create_writes_movement_and_issuance_ledger_entries(self):
        product = self._make_moved_product()
        op = self._consume(product)

        movement = ProductLedgerEntry.objects.filter(
            product=product,
            entry_type=ProductLedgerEntry.EntryType.CONSUMPTION_MOVEMENT,
        )
        issuance = ProductLedgerEntry.objects.filter(
            product=product,
            entry_type=ProductLedgerEntry.EntryType.CONSUMPTION_ISSUANCE,
        )
        self.assertTrue(movement.exists(), "CONSUMPTION_MOVEMENT ledger entry missing")
        self.assertTrue(issuance.exists(), "CONSUMPTION_ISSUANCE ledger entry missing")

        self.assertEqual(movement.first().quantity_delta, Decimal("-5.00"))
        self.assertEqual(movement.first().value_delta, Decimal("-500.00"))
        self.assertEqual(issuance.first().quantity_delta, Decimal("-5.00"))
        self.assertEqual(issuance.first().value_delta, Decimal("-500.00"))

    # ------------------------------------------------------------------
    # Product status
    # ------------------------------------------------------------------

    def test_create_marks_product_consumed(self):
        product = self._make_moved_product()
        self._consume(product)

        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.CONSUMED)

    def test_consumed_product_is_physically_moved(self):
        product = self._make_moved_product()
        self._consume(product)

        product.refresh_from_db()
        self.assertTrue(product.is_physically_moved)
        self.assertFalse(product.is_obligated_only)

    def test_consumed_product_validate_active_blocks_reuse(self):
        product = self._make_moved_product()
        self._consume(product)

        product.refresh_from_db()
        with self.assertRaises(ValidationError):
            product.validate_active()

        # Reversal of a consumption must still be allowed
        product.validate_active(allow_reversal=True)

    # ------------------------------------------------------------------
    # One-shot transaction behaviour (unchanged)
    # ------------------------------------------------------------------

    def test_create_creates_issuance_and_payment_transactions(self):
        product = self._make_moved_product()
        op = self._consume(product)

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 2)
        self.assertTrue(
            transactions.filter(type=TransactionType.CONSUMPTION_ISSUANCE).exists()
        )
        self.assertTrue(
            transactions.filter(type=TransactionType.CONSUMPTION_PAYMENT).exists()
        )

    def test_create_is_fully_settled(self):
        product = self._make_moved_product(qty=Decimal("2.00"), price=Decimal("50.00"))
        op = self._consume(product, qty=Decimal("2.00"), price=Decimal("50.00"))

        self.assertEqual(op.amount_settled, Decimal("100.00"))
        self.assertTrue(op.is_fully_settled)
        self.assertEqual(op.amount_remaining_to_settle, Decimal("0.00"))
