from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InventoryMovementLine,
    Product,
    ProductTemplate,
)
from apps.app_inventory.stock import inventory_value, movement_state
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_project_entity,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import DeathOperation, PurchaseOperation

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_officer(username="officer"):
    return User.objects.create_user(
        username=username, password="testpass", is_staff=True
    )


def _make_person_entity(name):
    return Entity.create(EntityType.PERSON, name=name)


def _make_project_entity(name):
    project = Entity.create(EntityType.PROJECT, name=name)
    return project


def _make_system_entity():
    return Entity.create(EntityType.SYSTEM)


# ---------------------------------------------------------------------------
# DeathCreateTest
# ---------------------------------------------------------------------------


class DeathCreateTest(TestCase):
    """
    Tests for death operation creation: config, validation, and the
    auto-settled issuance + payment transactions.

    A death removes an existing Animal/Batch from active inventory with no
    cash flow — the project's asset value is written off to the system entity.
    """

    def setUp(self):
        self.system_entity = _make_system_entity()
        self.officer_user = _make_officer()

        self.project_entity = _make_project_entity("Test Farm Project")

    def _make_op(self, **kwargs):
        defaults = dict(
            source=self.project_entity,
            destination=self.system_entity,
            amount=Decimal("500.00"),
            operation_type=OperationType.DEATH,
            date=date.today(),
            description="Test death",
            officer=self.officer_user,
        )
        defaults.update(kwargs)
        return DeathOperation(**defaults)

    # ------------------------------------------------------------------
    # Config flags
    # ------------------------------------------------------------------

    def test_has_category_config_is_false(self):
        self.assertFalse(DeathOperation.has_category)

    def test_can_pay_config_is_false(self):
        self.assertFalse(DeathOperation.can_pay)

    def test_is_one_shot_operation_config_is_false(self):
        """No payment mixin → the one-shot flag is not set for Death."""
        self.assertFalse(DeathOperation._is_one_shot_operation)

    def test_is_partially_payable_config_is_false(self):
        self.assertFalse(DeathOperation.is_partially_payable)

    # ------------------------------------------------------------------
    # No accounting transactions — Death is a stock event
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

    # ------------------------------------------------------------------
    # Source validation — must be a Project entity
    # ------------------------------------------------------------------

    def test_source_must_be_a_project_entity(self):
        non_project = _make_person_entity("Not A Project")
        op = self._make_op(source=non_project)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_world_entity_raises_validation_error(self):
        world_entity = Entity.create(EntityType.WORLD)
        op = self._make_op(source=world_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_system_entity_raises_validation_error(self):
        # The System entity already exists (setUp) — only one is allowed. Use it
        # directly as the source; clean_source must reject it (not a Project).
        op = self._make_op(source=self.system_entity, destination=self.project_entity)
        with self.assertRaises(ValidationError):
            op.save()

    def test_source_must_be_active(self):
        self.project_entity.active = False
        self.project_entity.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Destination validation — must be the System entity
    # ------------------------------------------------------------------

    def test_destination_must_be_system_entity(self):
        non_system = _make_project_entity("Not The System")
        op = self._make_op(destination=non_system)
        with self.assertRaises(ValidationError):
            op.save()

    def test_destination_person_entity_raises_validation_error(self):
        person = _make_person_entity("Some Person")
        op = self._make_op(destination=person)
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
        op = self._make_op(amount=Decimal("-50.00"))
        with self.assertRaises(ValidationError):
            op.save()

    # ------------------------------------------------------------------
    # Officer validation
    # ------------------------------------------------------------------

    def test_officer_must_be_a_staff_user(self):
        non_staff = User.objects.create_user(
            username="non_staff", password="testpass", is_staff=False
        )
        op = self._make_op(officer=non_staff)
        with self.assertRaises(ValidationError):
            op.save()

    def test_officer_must_be_active(self):
        """VC7 — an inactive officer cannot record a death."""
        self.officer_user.is_active = False
        self.officer_user.save()

        op = self._make_op()
        with self.assertRaises(ValidationError):
            op.save()


# ---------------------------------------------------------------------------
# DeathCreateInventoryTest — full create pipeline effects (SC3/SC5/SC7/SC9)
# ---------------------------------------------------------------------------


class DeathCreateInventoryTest(TestCase):
    """Death-specific inventory effects of the full ``DeathOperation.create()``
    pipeline: auto outbound movement lines (SC3), status DEAD (SC4/SC8), the
    inventory value dropping exactly once (SC5/SC9), and the fund balance
    staying untouched (SC7)."""

    def setUp(self):
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = make_user()
        self.project_entity = make_project_entity("Test Farm Project")
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        Stakeholder.objects.create(
            parent=self.project_entity,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        # DEATH applies to livestock — ANIMAL templates can die.
        self.template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            default_unit="Head",
        )

    def _make_moved_product(self, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Return an ACTIVE, physically-moved animal owned by the project."""
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

    def _death(self, product, qty=Decimal("5.00"), price=Decimal("100.00")):
        """Drive the full DeathOperation.create() pipeline with a formset."""
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
        return DeathOperation.create(
            operation_type=OperationType.DEATH,
            source=self.project_entity,
            destination=self.system_entity,
            amount=(qty * price).quantize(Decimal("0.01")),
            date=date.today(),
            description="Test death",
            officer=self.officer_user,
            amount_paid=Decimal("0.00"),
            raw_post=raw_post,
            project=self.project_entity,
        )

    # ------------------------------------------------------------------
    # SC3 — auto outbound movement lines
    # ------------------------------------------------------------------

    def test_create_auto_creates_outbound_movement_line(self):
        """SC3 — a death auto-creates one outbound movement line per item at
        the item quantity, valued at the product's carried cost."""
        product = self._make_moved_product()
        op = self._death(product)

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

    def test_create_movement_line_uses_selected_product(self):
        """The movement line links the exact product chosen in the form."""
        product = self._make_moved_product()
        op = self._death(product)

        ml = op.movement_lines.first()
        self.assertEqual(ml.product.pk, product.pk)
        self.assertEqual(Product.objects.filter(pk=product.pk).count(), 1)

    def test_create_multiple_items_each_get_a_movement_line(self):
        """One auto outbound line per invoice item in the death."""
        product_a = self._make_moved_product()
        product_b = self._make_moved_product()

        raw_post = {
            "items-TOTAL_FORMS": "2",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-quantity": "5.00",
            "items-0-unit_price": "100.00",
            "items-0-description": "",
            "items-0-selected_product": str(product_a.pk),
            "items-0-DELETE": "",
            "items-1-id": "",
            "items-1-quantity": "5.00",
            "items-1-unit_price": "100.00",
            "items-1-description": "",
            "items-1-selected_product": str(product_b.pk),
            "items-1-DELETE": "",
        }
        op = DeathOperation.create(
            operation_type=OperationType.DEATH,
            source=self.project_entity,
            destination=self.system_entity,
            amount=Decimal("1000.00"),
            date=date.today(),
            description="Test death",
            officer=self.officer_user,
            amount_paid=Decimal("0.00"),
            raw_post=raw_post,
            project=self.project_entity,
        )

        self.assertEqual(op.movement_lines.count(), 2)
        self.assertEqual(
            set(op.movement_lines.values_list("product_id", flat=True)),
            {product_a.pk, product_b.pk},
        )
        self.assertEqual(
            len(set(op.movement_lines.values_list("group_key", flat=True))),
            1,
            "All auto-created lines share one group key",
        )

    # ------------------------------------------------------------------
    # SC4/SC8 — product status DEAD; SC5/SC9 — inventory value drops once
    # ------------------------------------------------------------------

    def test_create_marks_product_dead(self):
        """SC4/SC8 — the written-off product becomes DEAD."""
        product = self._make_moved_product()
        self._death(product)

        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.DEAD)

    def test_create_drops_movement_state_to_zero(self):
        """The product's movement state falls to zero after a full write-off."""
        product = self._make_moved_product(qty=Decimal("5.00"), price=Decimal("100.00"))
        self._death(product, qty=Decimal("5.00"), price=Decimal("100.00"))

        state = movement_state(product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("0.00"))
        self.assertEqual(state["value"], Decimal("0.00"))

    def test_create_drops_inventory_value_once(self):
        """SC5/SC9 — inventory_value() drops by the carried cost exactly once."""
        product = self._make_moved_product(qty=Decimal("5.00"), price=Decimal("100.00"))
        before = inventory_value(self.project_entity, as_of=date.today())
        self.assertEqual(before, Decimal("500.00"))

        self._death(product, qty=Decimal("5.00"), price=Decimal("100.00"))

        after = inventory_value(self.project_entity, as_of=date.today())
        self.assertEqual(after, Decimal("0.00"))

    # ------------------------------------------------------------------
    # SC7 — fund balance unchanged
    # ------------------------------------------------------------------

    def test_create_does_not_drain_fund_balance(self):
        """SC7 — a death never touches the project's fund balance."""
        product = self._make_moved_product()
        balance_before = self.project_entity.balance_at(date.today())

        self._death(product)

        self.assertEqual(
            self.project_entity.balance_at(date.today()),
            balance_before,
            "Death must not drain the fund balance (no payment types).",
        )

    def test_create_leaves_payables_receivables_unchanged(self):
        """A death creates no obligations — the project's payables/receivables
        are exactly as before the death (the setup purchase's payable persists)."""
        product = self._make_moved_product()
        self.project_entity.refresh_from_db()
        payables_before = self.project_entity.payables
        receivables_before = self.project_entity.receivables

        self._death(product)

        self.project_entity.refresh_from_db()
        self.assertEqual(self.project_entity.payables, payables_before)
        self.assertEqual(self.project_entity.receivables, receivables_before)

    # ------------------------------------------------------------------
    # VC10 — die-able template gating (ANIMAL **and** can_die=True)
    # ------------------------------------------------------------------

    def test_non_animal_template_rejected_for_death(self):
        """VC10 — a FEED template (nature != ANIMAL, can_die=False) is
        rejected at invoice-item validation for a death."""
        feed = ProductTemplate.objects.create(
            name="Feed Mix",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
        )
        feed_product = Product.objects.create(
            product_template=feed,
            entity=self.project_entity,
            unit_price=Decimal("100.00"),
            quantity=5,
        )

        raw_post = {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-quantity": "5.00",
            "items-0-unit_price": "100.00",
            "items-0-description": "",
            "items-0-selected_product": str(feed_product.pk),
            "items-0-DELETE": "",
        }
        with self.assertRaises((ValidationError, ValueError)):
            DeathOperation.create(
                operation_type=OperationType.DEATH,
                source=self.project_entity,
                destination=self.system_entity,
                amount=Decimal("500.00"),
                date=date.today(),
                description="Test death",
                officer=self.officer_user,
                amount_paid=Decimal("0.00"),
                raw_post=raw_post,
                project=self.project_entity,
            )
