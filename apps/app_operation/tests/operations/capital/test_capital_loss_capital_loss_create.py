from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import InventoryMovementLine, Product, ProductTemplate
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalLossOperation
from apps.app_transaction.transaction_type import TransactionType

User = get_user_model()


class CapitalLossCreateTest(TestCase):
    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)

        self.officer_user = User.objects.create_user(
            username="officer", password="testpass", is_staff=True
        )

        # Source: active project entity
        self.project_entity = Entity.create(EntityType.PROJECT, name="Test Project")

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.project_entity,
            destination=self.system_entity,
            amount=Decimal("500.00"),
            operation_type=OperationType.CAPITAL_LOSS,
            date=date.today(),
            description="Test capital loss",
            officer=self.officer_user,
        )
        defaults.update(kwargs)
        return CapitalLossOperation(**defaults)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_creates_issuance_and_payment_transactions(self):
        op = self._make_op()
        op.save()

        self.assertIsNotNone(op.pk)

        transactions = op.get_all_transactions()
        self.assertEqual(transactions.count(), 2)

        self.assertTrue(
            transactions.filter(type=TransactionType.CAPITAL_LOSS_ISSUANCE).exists(),
            "Issuance transaction should be created",
        )
        self.assertTrue(
            transactions.filter(type=TransactionType.CAPITAL_LOSS_PAYMENT).exists(),
            "Payment transaction should be created",
        )

    def test_transaction_amounts_match_operation(self):
        op = self._make_op(amount=Decimal("300.00"))
        op.save()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.amount, Decimal("300.00"))

    def test_transaction_funds_are_correct(self):
        op = self._make_op()
        op.save()

        for tx in op.get_all_transactions():
            self.assertEqual(tx.source, self.project_entity)
            self.assertEqual(tx.target, self.system_entity)

    def test_is_fully_settled_after_creation(self):
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        self.assertEqual(op.amount_settled, Decimal("500.00"))
        self.assertTrue(op.is_fully_settled)
        self.assertEqual(op.amount_remaining_to_settle, Decimal("0.00"))

    def test_project_fund_decreases_by_loss_amount(self):
        # Seed some balance so the project can absorb the loss
        from apps.app_operation.models.proxies import CapitalGainOperation

        seed = CapitalGainOperation(
            source=self.system_entity,
            destination=self.project_entity,
            amount=Decimal("1000.00"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=date.today(),
            description="Seed balance",
            officer=self.officer_user,
        )
        seed.save()

        balance_before = self.project_entity.balance

        op = self._make_op(amount=Decimal("750.00"))
        op.save()

        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            balance_before - Decimal("750.00"),
        )

    # ------------------------------------------------------------------
    # Source validation
    # ------------------------------------------------------------------

    def test_source_system_entity_raises_validation_error(self):
        op = self._make_op(source=self.system_entity, destination=self.system_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_project_must_be_active(self):
        self.project_entity.active = False
        self.project_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_fund_must_be_active(self):
        self.project_entity.active = False
        self.project_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation
    # ------------------------------------------------------------------

    def test_destination_must_be_system_entity(self):
        non_system_person = Entity.create(EntityType.PERSON, name="Non System Person")
        op = self._make_op(destination=non_system_person)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_world_entity_raises_validation_error(self):
        world_entity = Entity.create(EntityType.WORLD)
        op = self._make_op(destination=world_entity)
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Amount validation
    # ------------------------------------------------------------------

    def test_amount_zero_raises_validation_error(self):
        op = self._make_op(amount=Decimal("0.00"))
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_negative_raises_validation_error(self):
        op = self._make_op(amount=Decimal("-100.00"))
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Officer validation
    # ------------------------------------------------------------------

    def test_officer_user_must_be_staff(self):
        non_staff_user = User.objects.create_user(
            username="non_staff", password="testpass", is_staff=False
        )

        op = self._make_op(officer=non_staff_user)
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_must_be_active(self):
        self.officer_user.is_active = False
        self.officer_user.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Immutability
    # ------------------------------------------------------------------

    def test_source_is_immutable(self):
        op = self._make_op()
        op.save()

        other_entity = Entity.create(EntityType.PROJECT, name="Other Project")

        op.source = other_entity
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_is_immutable(self):
        op = self._make_op()
        op.save()
        other_entity = Entity.create(EntityType.PROJECT, name="Other Project")

        op.destination = other_entity
        with self.assertRaises(ValidationError):
            op.save()

    def test_amount_is_immutable(self):
        op = self._make_op()
        op.save()

        op.amount = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # One-shot constraint
    # ------------------------------------------------------------------

    def test_one_shot_prevents_second_payment(self):
        op = self._make_op()
        op.save()

        with self.assertRaises(ValidationError):
            op.create_payment_transaction(
                amount=op.amount,
                officer=self.officer_user,
                date=date.today(),
            )

    # ------------------------------------------------------------------
    # check_balance_on_payment
    # ------------------------------------------------------------------

    def test_check_balance_on_payment_is_disabled(self):
        """Destination is the system entity; no fund balance gate on payment."""
        self.assertFalse(CapitalLossOperation.check_balance_on_payment)

    # ------------------------------------------------------------------
    # Deficit behaviour — a loss-making project can go further into debt
    # ------------------------------------------------------------------

    def test_zero_balance_project_can_record_capital_loss(self):
        """A project with no funds may still record a capital loss."""
        self.project_entity.refresh_from_db()
        self.assertEqual(self.project_entity.balance, Decimal("0.00"))

        op = self._make_op(amount=Decimal("500.00"))
        op.save()  # must NOT raise ValidationError for insufficient funds

        self.project_entity.refresh_from_db()
        self.assertEqual(self.project_entity.balance, Decimal("-500.00"))

    def test_insufficient_balance_project_goes_into_deficit(self):
        """A loss larger than the fund balance drives the fund into deficit."""
        # Seed a small balance, then record a loss that exceeds it.
        from apps.app_operation.models.proxies import CapitalGainOperation

        seed = CapitalGainOperation(
            source=self.system_entity,
            destination=self.project_entity,
            amount=Decimal("100.00"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=date.today(),
            description="Seed balance",
            officer=self.officer_user,
        )
        seed.save()

        self.project_entity.refresh_from_db()
        self.assertEqual(self.project_entity.balance, Decimal("100.00"))

        op = self._make_op(amount=Decimal("500.00"))
        op.save()  # must NOT raise ValidationError for insufficient funds

        self.project_entity.refresh_from_db()
        self.assertEqual(self.project_entity.balance, Decimal("-400.00"))

    def test_loss_making_project_can_record_further_losses(self):
        """A project already in deficit can keep recording more losses."""
        op1 = self._make_op(amount=Decimal("300.00"))
        op1.save()

        op2 = self._make_op(amount=Decimal("200.00"))
        op2.save()

        op3 = self._make_op(amount=Decimal("150.00"))
        op3.save()

        self.project_entity.refresh_from_db()
        self.assertEqual(self.project_entity.balance, Decimal("-650.00"))

    def test_capital_loss_is_value_only_no_movement_line(self):
        """A capital loss never creates an InventoryMovementLine and keeps the
        product ACTIVE — quantity is untouched, only value is written down."""
        template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.BATCH,
            default_unit="Head",
        )
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        from apps.app_inventory.models import InvoiceItem

        item = InvoiceItem.objects.create(
            operation=op,
            product_template=template,
            quantity=Decimal("1.00"),
            unit_price=Decimal("500.00"),
        )
        product = Product.objects.create(
            product_template=template,
            unit_price=Decimal("500.00"),
            quantity=1,
        )
        product.invoice_items.add(item)

        self.assertEqual(product.status, Product.Status.ACTIVE)
        self.assertFalse(
            InventoryMovementLine.objects.filter(operation=op).exists(),
            "Capital loss must not create an InventoryMovementLine.",
        )
