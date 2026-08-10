from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import (
    InventoryMovementLine,
    Product,
    ProductLedgerEntry,
    ProductTemplate,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import BirthOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


class BirthCreateTest(TestCase):
    """Dedicated tests for Birth operation creation.

    A birth records a new animal/batch entering the project's inventory with
    no cash flow — the System entity issues the asset value on the project's
    behalf.  One-shot: issuance + payment fire on save; an inbound movement
    line is auto-created and the product is created lazily (ACTIVE).
    """

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )
        self.project_entity = Entity.create(
            EntityType.PROJECT, name="Test Farm Project"
        )
        # BIRTH is allowed for ANIMAL nature only
        self.template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
        )
        self.template.entities.add(self.project_entity)

    def _birth(self, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Drive the full BirthOperation.create() pipeline with a formset."""
        raw_post = {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-product_template": str(self.template.pk),
            "items-0-quantity": str(qty),
            "items-0-unit_price": str(price),
            "items-0-description": "",
            "items-0-unique_id": "",
            "items-0-DELETE": "",
        }
        return BirthOperation.create(
            operation_type=OperationType.BIRTH,
            source=self.system_entity,
            destination=self.project_entity,
            amount=(qty * price).quantize(Decimal("0.01")),
            date=date.today(),
            description="Test birth",
            officer=self.officer_user,
            amount_paid=Decimal("0.00"),
            raw_post=raw_post,
            project=self.project_entity,
        )

    # ------------------------------------------------------------------
    # Config flags
    # ------------------------------------------------------------------

    def test_has_category_config_is_false(self):
        self.assertFalse(BirthOperation.has_category)

    def test_category_required_config_is_false(self):
        self.assertFalse(BirthOperation.category_required)

    def test_can_pay_config_is_false(self):
        self.assertFalse(BirthOperation.can_pay)

    def test_is_one_shot_operation_config_is_true(self):
        self.assertTrue(BirthOperation._is_one_shot_operation)

    def test_is_partially_payable_config_is_false(self):
        self.assertFalse(BirthOperation.is_partially_payable)

    def test_check_balance_on_payment_is_disabled(self):
        """Source is the system entity — exempt from fund balance validation."""
        self.assertFalse(BirthOperation.check_balance_on_payment)

    def test_creates_assets_config_is_true(self):
        self.assertTrue(BirthOperation.creates_assets)

    # ------------------------------------------------------------------
    # Happy path — issuance + payment auto-created on save
    # ------------------------------------------------------------------

    def test_save_creates_issuance_and_payment_transactions(self):
        op = self._birth()

        self.assertIsNotNone(op.pk)

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 2)

        self.assertTrue(
            transactions.filter(type=TransactionType.BIRTH_ISSUANCE).exists(),
            "Issuance transaction should be created on save",
        )
        self.assertTrue(
            transactions.filter(type=TransactionType.BIRTH_PAYMENT).exists(),
            "Payment transaction should be created on save — one-shot operation",
        )

    def test_transaction_direction_is_system_to_project(self):
        op = self._birth()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.source, self.system_entity)
            self.assertEqual(tx.target, self.project_entity)

    def test_transaction_amounts_match_operation(self):
        op = self._birth(qty=Decimal("3.00"), price=Decimal("150.00"))

        for tx in op.get_all_transactions():
            self.assertEqual(tx.amount, Decimal("450.00"))

    def test_is_fully_settled_after_creation(self):
        op = self._birth()

        self.assertEqual(op.amount_settled, Decimal("500.00"))
        self.assertTrue(op.is_fully_settled)
        self.assertEqual(op.amount_remaining_to_settle, Decimal("0.00"))

    # ------------------------------------------------------------------
    # Source validation — must be the System entity
    # ------------------------------------------------------------------

    def test_source_must_be_system_entity(self):
        non_system = Entity.create(EntityType.PROJECT, name="Not The System")
        op = self._birth()
        op.source = non_system
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_person_entity_raises_validation_error(self):
        person = Entity.create(EntityType.PERSON, name="Some Person")
        op = self._birth()
        op.source = person
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation — must be a Project entity
    # ------------------------------------------------------------------

    def test_destination_must_be_project_entity(self):
        person = Entity.create(EntityType.PERSON, name="Some Person")
        op = self._birth()
        op.destination = person
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_world_entity_raises_validation_error(self):
        world = Entity.create(EntityType.WORLD)
        op = self._birth()
        op.destination = world
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Amount validation
    # ------------------------------------------------------------------

    def test_amount_zero_raises_validation_error(self):
        op = BirthOperation(
            source=self.system_entity,
            destination=self.project_entity,
            amount=Decimal("0.00"),
            operation_type=OperationType.BIRTH,
            date=date.today(),
            description="Test birth",
            officer=self.officer_user,
        )
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_negative_raises_validation_error(self):
        op = BirthOperation(
            source=self.system_entity,
            destination=self.project_entity,
            amount=Decimal("-100.00"),
            operation_type=OperationType.BIRTH,
            date=date.today(),
            description="Test birth",
            officer=self.officer_user,
        )
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Officer validation
    # ------------------------------------------------------------------

    def test_officer_must_be_a_staff_user(self):
        non_staff = User.objects.create_user(
            username="non_staff", password="testpass", is_staff=False
        )
        op = self._birth()
        op.officer = non_staff
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_must_be_active(self):
        self.officer_user.is_active = False
        self.officer_user.save()

        with self.assertRaises(ValidationError):
            self._birth()

    # ------------------------------------------------------------------
    # Auto movement line + lazy product creation
    # ------------------------------------------------------------------

    def test_create_auto_creates_inbound_movement_lines(self):
        """INDIVIDUAL birth creates one movement line per head."""
        op = self._birth()

        self.assertEqual(op.movement_lines.count(), 5)
        for ml in op.movement_lines.all():
            self.assertEqual(ml.invoice_item, op.items.get())
            self.assertEqual(ml.quantity, Decimal("1.00"))
            self.assertEqual(ml.officer, self.officer_user)
            self.assertEqual(ml.date, op.date)
            self.assertTrue(ml.group_key, "Auto-created lines share a group key")
            self.assertIsNone(ml.reversal_of)

    def test_movement_lines_have_lazily_created_tagged_products(self):
        """Each movement line lazy-creates its own tagged Product (qty=1)."""
        op = self._birth()

        self.assertEqual(op.movement_lines.count(), 5)
        products = list(op.movement_lines.select_related("product").all())
        for ml in products:
            self.assertIsNotNone(ml.product, "Product should be lazily created")
            self.assertEqual(ml.product.product_template, self.template)
            self.assertEqual(ml.product.quantity, 1)
            self.assertTrue(ml.product.unique_id, "Each animal has a unique tag")
        tags = [ml.product.unique_id for ml in products]
        self.assertEqual(len(set(tags)), len(tags), "Tags must be unique")

    def test_created_product_is_active(self):
        op = self._birth()

        product = op.movement_lines.first().product
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.ACTIVE)

    # ------------------------------------------------------------------
    # Ledger entries
    # ------------------------------------------------------------------

    def test_create_writes_movement_and_issuance_ledger_entries(self):
        op = self._birth()
        item = op.items.get()
        product = op.movement_lines.first().product

        movement = ProductLedgerEntry.objects.filter(
            product=product,
            entry_type=ProductLedgerEntry.EntryType.BIRTH_MOVEMENT,
        )
        issuance = ProductLedgerEntry.objects.filter(
            invoice_item=item,
            entry_type=ProductLedgerEntry.EntryType.BIRTH_ISSUANCE,
        )
        self.assertTrue(movement.exists(), "BIRTH_MOVEMENT ledger entry missing")
        self.assertTrue(issuance.exists(), "BIRTH_ISSUANCE ledger entry missing")

        # Each individually tracked animal carries its own movement (qty=1);
        # the contract-level issuance covers the full quantity.
        self.assertEqual(movement.first().quantity_delta, Decimal("1.00"))
        self.assertEqual(movement.first().value_delta, Decimal("100.00"))
        self.assertEqual(issuance.first().quantity_delta, Decimal("5.00"))
        self.assertEqual(issuance.first().value_delta, Decimal("500.00"))

    # ------------------------------------------------------------------
    # One-shot constraint
    # ------------------------------------------------------------------

    def test_one_shot_prevents_second_payment(self):
        op = self._birth()

        with self.assertRaises(ValidationError):
            op.create_payment_transaction(
                amount=op.amount,
                officer=self.officer_user,
                date=date.today(),
            )
