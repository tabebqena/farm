from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import (
    InventoryMovementLine,
    Product,
    ProductTemplate,
)
from apps.app_inventory.stock import movement_state
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import BirthOperation

User = get_user_model()


class BirthCreateTest(TestCase):
    """Dedicated tests for Birth operation creation.

    A birth records a new animal/batch entering the project's inventory with
    no cash flow.  Birth is a stock event, NOT an accounting operation: it
    creates NO Transaction rows, has no payment/settlement machinery, and is
    still assigned to a financial period (and blocked inside a closed one).
    An inbound movement line is auto-created and the product is created
    lazily (ACTIVE).
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

    def _birth(
        self, qty=Decimal("5.00"), price=Decimal("100.00"), template=None
    ):
        """Drive the full BirthOperation.create() pipeline with a formset."""
        template = template or self.template
        raw_post = {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-product_template": str(template.pk),
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

    def test_is_one_shot_operation_config_is_false(self):
        """No payment mixin → the one-shot flag is not set for Birth."""
        self.assertFalse(BirthOperation._is_one_shot_operation)

    def test_is_partially_payable_config_is_false(self):
        self.assertFalse(BirthOperation.is_partially_payable)

    def test_check_balance_on_payment_is_disabled(self):
        """Source is the system entity — exempt from fund balance validation."""
        self.assertFalse(BirthOperation.check_balance_on_payment)

    def test_creates_assets_config_is_true(self):
        self.assertTrue(BirthOperation.creates_assets)

    def test_has_invoice_config_is_true(self):
        """Birth carries invoice items + auto inventory movements."""
        self.assertTrue(BirthOperation.has_invoice)

    def test_has_repayment_config_is_false(self):
        """No repayment machinery on a birth."""
        self.assertFalse(BirthOperation.has_repayment)

    def test_can_create_movement_is_false(self):
        """Birth has no manual movement screen — inbound lines are auto-created."""
        op = BirthOperation(
            source=self.system_entity,
            destination=self.project_entity,
            amount=Decimal("100.00"),
            operation_type=OperationType.BIRTH,
            date=date.today(),
            description="Test birth",
            officer=self.officer_user,
        )
        self.assertFalse(op.can_create_movement)

    # ------------------------------------------------------------------
    # No accounting transactions — Birth is a stock event
    # ------------------------------------------------------------------

    def test_save_creates_no_transactions(self):
        """A birth is a stock event: it must NOT create any Transaction."""
        op = self._birth()

        self.assertIsNotNone(op.pk)
        self.assertEqual(op.get_all_transactions().count(), 0)

    def test_no_settlement_or_payment_machinery(self):
        """Birth does not inherit the payment/settlement/repayment members."""
        op = self._birth()
        for member in (
            "amount_settled",
            "is_fully_settled",
            "amount_remaining_to_settle",
            "create_payment_transaction",
            "create_issuance_transaction",
            "payment_transactions",
            "repayable_amount",
            "amount_repayed",
        ):
            self.assertFalse(hasattr(op, member), member)

    def test_period_is_assigned_on_creation(self):
        """Birth still respects financial periods — a covering period is assigned."""
        op = self._birth()
        self.assertIsNotNone(op.period, "A covering financial period must be assigned")

    def test_effective_amount_equals_amount(self):
        """Not adjustable → the effective amount is the plain amount."""
        op = self._birth()
        self.assertEqual(op.effective_amount, op.amount)

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
    # Immutability (IM1/IM2/IM3)
    # ------------------------------------------------------------------

    def test_source_is_immutable_after_save(self):
        op = self._birth()
        other_project = Entity.create(EntityType.PROJECT, name="Other Project")

        op.source = other_project
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable_after_save(self):
        op = self._birth()
        other_project = Entity.create(EntityType.PROJECT, name="Other Project 2")

        op.destination = other_project
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_is_immutable_after_save(self):
        op = self._birth()

        op.amount = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Template nature gating — BIRTH is ANIMAL-only (VC10)
    # ------------------------------------------------------------------

    def test_non_animal_template_rejected_for_birth(self):
        """VC10 — BIRTH only accepts ANIMAL templates; a COMMODITY (FEED)
        template is rejected at invoice-item validation."""
        feed = ProductTemplate.objects.create(
            name="Feed Mix",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            tracking_mode=ProductTemplate.TrackingMode.COMMODITY,
            default_unit="Kg",
        )
        feed.entities.add(self.project_entity)

        # The model-level InvoiceItem.clean() raises ValidationError; the
        # inline formset re-wraps it into ValueError at save time.
        with self.assertRaises((ValidationError, ValueError)):
            self._birth(template=feed, qty=Decimal("1.00"), price=Decimal("100.00"))

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

        for ml in op.movement_lines.all():
            ml.product.refresh_from_db()
            self.assertEqual(
                ml.product.status, Product.Status.ACTIVE, ml.product.unique_id
            )

    # ------------------------------------------------------------------
    # Movement lines / stock state
    # ------------------------------------------------------------------

    def test_create_writes_movement_and_issuance_ledger_entries(self):
        op = self._birth()
        products = list(op.movement_lines.select_related("product").all())

        # Each individually tracked animal carries its own movement (qty=1)
        # and is physically present at its carried value.
        self.assertEqual(len(products), 5)
        for ml in products:
            state = movement_state(ml.product, as_of=date.today())
            self.assertEqual(state["quantity"], Decimal("1.00"), ml.product.unique_id)
            self.assertEqual(state["value"], Decimal("100.00"))

    # ------------------------------------------------------------------
    # Fund balance — Birth is non-cash (SC10)
    # ------------------------------------------------------------------

    def test_project_fund_unchanged_by_birth(self):
        """SC10 — a birth is non-cash: the project's fund balance is untouched."""
        balance_before = self.project_entity.balance
        self._birth()

        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            balance_before,
            "Birth must not change the fund balance.",
        )

    # ------------------------------------------------------------------
    # One-shot constraint
    # ------------------------------------------------------------------

    def test_cannot_be_paid(self):
        """Birth has no payment machinery — no standalone pay action exists."""
        op = self._birth()
        self.assertFalse(hasattr(op, "create_payment_transaction"))
