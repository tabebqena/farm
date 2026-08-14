from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import (
    InventoryMovementLine,
    InvoiceItem,
    Product,
    ProductCapitalValuation,
    ProductTemplate,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalLossOperation

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
    # No accounting transactions — Capital Loss is a stock event
    # ------------------------------------------------------------------

    def test_save_creates_no_transactions(self):
        op = self._make_op()
        op.save()

        self.assertIsNotNone(op.pk)
        self.assertEqual(op.get_all_transactions().count(), 0)

    def test_period_is_assigned_and_no_settlement_machinery(self):
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        self.assertIsNotNone(op.period, "A covering financial period is assigned")
        self.assertFalse(hasattr(op, "amount_settled"))
        self.assertFalse(hasattr(op, "is_fully_settled"))
        self.assertFalse(hasattr(op, "create_payment_transaction"))

    def test_project_fund_unchanged_by_loss_amount(self):
        """A capital loss is non-cash and non-accounting — the fund balance is
        not drained; the loss is reflected in movement-based inventory value."""
        balance_before = self.project_entity.balance

        op = self._make_op(amount=Decimal("750.00"))
        op.save()

        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            balance_before,
            "Capital loss is non-cash — the fund balance must be unchanged.",
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
    # No payment machinery
    # ------------------------------------------------------------------

    def test_cannot_be_paid(self):
        """Capital Loss has no payment machinery — no standalone pay action."""
        op = self._make_op()
        op.save()
        self.assertFalse(hasattr(op, "create_payment_transaction"))

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
        """A project with no funds may still record a capital loss (no balance
        gate), and the loss is non-cash — the fund balance stays at zero."""
        self.project_entity.refresh_from_db()
        self.assertEqual(self.project_entity.balance, Decimal("0.00"))

        op = self._make_op(amount=Decimal("500.00"))
        op.save()  # must NOT raise ValidationError for insufficient funds

        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            Decimal("0.00"),
            "Capital loss is non-cash — the fund balance is unchanged.",
        )

    def test_loss_larger_than_balance_is_allowed_non_cash(self):
        """A loss larger than any fund balance is allowed (no balance gate),
        and is non-cash — no fund deficit is created."""
        op = self._make_op(amount=Decimal("500.00"))
        op.save()  # must NOT raise ValidationError for insufficient funds

        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            Decimal("0.00"),
            "Capital loss is non-cash — the fund balance is unchanged.",
        )

    def test_loss_making_project_can_record_further_losses(self):
        """A project can keep recording losses (no balance gate); each loss is
        non-cash so the fund balance is unchanged."""
        op1 = self._make_op(amount=Decimal("300.00"))
        op1.save()

        op2 = self._make_op(amount=Decimal("200.00"))
        op2.save()

        op3 = self._make_op(amount=Decimal("150.00"))
        op3.save()

        self.project_entity.refresh_from_db()
        self.assertEqual(
            self.project_entity.balance,
            Decimal("0.00"),
            "Capital losses are non-cash — the fund balance is unchanged.",
        )

    def test_capital_loss_is_value_only_no_movement_line(self):
        """A capital loss never creates an InventoryMovementLine or an
        InvoiceItem and keeps the product ACTIVE — quantity is untouched, only
        value is written down via a ProductCapitalValuation row."""
        template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
        )
        op = self._make_op(amount=Decimal("500.00"))
        op.save()

        product = Product.objects.create(
            product_template=template,
            entity=self.project_entity,
            unit_price=Decimal("500.00"),
            quantity=1,
        )
        op.add_valuation(
            product=product, amount=Decimal("-500.00"), officer=self.officer_user
        )

        self.assertEqual(product.status, Product.Status.ACTIVE)
        self.assertFalse(
            InventoryMovementLine.objects.filter(operation=op).exists(),
            "Capital loss must not create an InventoryMovementLine.",
        )
        self.assertFalse(
            InvoiceItem.objects.filter(operation=op).exists(),
            "Capital loss must not create an InvoiceItem.",
        )
        self.assertTrue(
            ProductCapitalValuation.objects.filter(operation=op, product=product).exists(),
            "Capital loss is recorded as a ProductCapitalValuation row.",
        )
