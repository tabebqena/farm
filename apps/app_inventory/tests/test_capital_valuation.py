"""Tests for the dedicated ProductCapitalValuation link table.

Capital Gain / Capital Loss are value-only: they record the signed valuation on a
``ProductCapitalValuation`` row instead of an ``InvoiceItem`` + M2M link. These
tests pin the new model's guards and the value/reversal behaviour (spec branches
SC4, SC5, SR5).
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InventoryMovementLine,
    InvoiceItem,
    Product,
    ProductCapitalValuation,
    ProductTemplate,
)
from apps.app_inventory.stock import capital_delta, inventory_value, movement_state
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice_item,
    make_operation,
    make_product,
    make_product_template,
    make_project_entity,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CapitalGainOperation,
    CapitalLossOperation,
    CorrectionOperation,
    PurchaseOperation,
)


class ProductCapitalValuationModelTest(TestCase):
    def setUp(self):
        self.officer = make_user()
        self.system = Entity.create(EntityType.SYSTEM)
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        self.project = make_project_entity("Farm")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.template = make_product_template()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_gain_op(self, amount=Decimal("500.00")):
        return make_operation(
            self.system,
            self.project,
            self.officer,
            CapitalGainOperation,
            OperationType.CAPITAL_GAIN,
            amount=amount,
        )

    def _make_loss_op(self, amount=Decimal("200.00")):
        return make_operation(
            self.project,
            self.system,
            self.officer,
            CapitalLossOperation,
            OperationType.CAPITAL_LOSS,
            amount=amount,
        )

    def _make_product(self, entity=None):
        return make_product(
            self.template, Decimal("100.00"), 1, entity or self.project
        )

    def _make_moved_product(self, qty=1, price=Decimal("100.00")):
        """A product physically moved into stock (purchase + movement line)."""
        purchase = make_operation(
            self.project,
            self.vendor,
            self.officer,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=(Decimal(qty) * price).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(purchase, self.template, Decimal(qty), price)
        product = make_product(self.template, price, qty, self.project)
        product.invoice_items.add(item)
        InventoryMovementLine.objects.create(
            operation=purchase,
            invoice_item=item,
            product=product,
            quantity=Decimal(qty),
            date=date.today(),
            officer=self.officer,
            notes="",
            group_key="val",
        )
        return product

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def test_gain_requires_positive_amount(self):
        op = self._make_gain_op()
        product = self._make_product()
        with self.assertRaises(ValidationError):
            op.add_valuation(
                product=product, amount=Decimal("-200.00"), officer=self.officer
            )

    def test_loss_requires_negative_amount(self):
        op = self._make_loss_op()
        product = self._make_product()
        with self.assertRaises(ValidationError):
            op.add_valuation(
                product=product, amount=Decimal("200.00"), officer=self.officer
            )

    def test_zero_amount_rejected(self):
        op = self._make_gain_op()
        product = self._make_product()
        with self.assertRaises(ValidationError):
            op.add_valuation(
                product=product, amount=Decimal("0.00"), officer=self.officer
            )

    def test_wrong_operation_type_rejected(self):
        """A non-capital operation cannot host a valuation row."""
        op = make_operation(
            self.system,
            self.project,
            self.officer,
            CorrectionOperation,
            OperationType.CORRECTION_CREDIT,
            amount=Decimal("100.00"),
        )
        product = self._make_product()
        entry = ProductCapitalValuation(
            operation=op,
            product=product,
            amount=Decimal("50.00"),
            date=date.today(),
            officer=self.officer,
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_ownership_guard_rejects_other_project_product(self):
        op = self._make_gain_op()
        other = make_project_entity("Other Farm")
        product = self._make_product(entity=other)
        with self.assertRaises(ValidationError):
            op.add_valuation(
                product=product, amount=Decimal("500.00"), officer=self.officer
            )

    def test_amount_immutable_after_save(self):
        op = self._make_gain_op()
        product = self._make_product()
        entry = op.add_valuation(
            product=product, amount=Decimal("500.00"), officer=self.officer
        )
        entry.amount = Decimal("999.00")
        with self.assertRaises(ValidationError):
            entry.save()

    # ------------------------------------------------------------------
    # SC5 — value-only: valuation row, but NO InvoiceItem / NO movement line
    # ------------------------------------------------------------------

    def test_gain_creates_valuation_row_no_invoice_no_movement(self):
        op = self._make_gain_op()
        product = self._make_product()
        entry = op.add_valuation(
            product=product, amount=Decimal("500.00"), officer=self.officer
        )

        self.assertIsNotNone(entry.pk)
        self.assertEqual(entry.amount, Decimal("500.00"))
        self.assertEqual(entry.operation, op)
        self.assertEqual(entry.product, product)
        self.assertFalse(
            type(op).has_invoice, "Capital Gain must not carry invoice items"
        )
        self.assertTrue(type(op).has_capital_valuation)
        self.assertEqual(
            InvoiceItem.objects.filter(operation=op).count(),
            0,
            "No InvoiceItem is created for a capital gain.",
        )
        self.assertEqual(
            InventoryMovementLine.objects.filter(operation=op).count(),
            0,
            "No InventoryMovementLine is created for a capital gain.",
        )

    # ------------------------------------------------------------------
    # SC4 — inventory value rises by the signed amount
    # ------------------------------------------------------------------

    def test_movement_state_value_rises_by_gain(self):
        product = self._make_moved_product(qty=1, price=Decimal("100.00"))
        before = movement_state(product)["value"]
        self.assertEqual(before, Decimal("100.00"))

        op = self._make_gain_op(amount=Decimal("500.00"))
        op.add_valuation(product=product, amount=Decimal("500.00"), officer=self.officer)

        self.assertEqual(capital_delta(product), Decimal("500.00"))
        self.assertEqual(movement_state(product)["value"], Decimal("600.00"))

    def test_inventory_value_rises_by_gain(self):
        product = self._make_moved_product(qty=1, price=Decimal("100.00"))
        before = inventory_value(self.project)
        self.assertEqual(before, Decimal("100.00"))

        op = self._make_gain_op(amount=Decimal("500.00"))
        op.add_valuation(product=product, amount=Decimal("500.00"), officer=self.officer)

        self.assertEqual(inventory_value(self.project), before + Decimal("500.00"))

    def test_movement_state_value_falls_by_loss(self):
        product = self._make_moved_product(qty=1, price=Decimal("100.00"))
        self.assertEqual(movement_state(product)["value"], Decimal("100.00"))

        op = self._make_loss_op(amount=Decimal("200.00"))
        op.add_valuation(product=product, amount=Decimal("-200.00"), officer=self.officer)

        self.assertEqual(capital_delta(product), Decimal("-200.00"))
        self.assertEqual(movement_state(product)["value"], Decimal("-100.00"))

    # ------------------------------------------------------------------
    # SR5 — reversal restores the value (op-level reversal)
    # ------------------------------------------------------------------

    def test_reverse_restores_value_to_baseline(self):
        product = self._make_moved_product(qty=1, price=Decimal("100.00"))

        op = self._make_gain_op(amount=Decimal("500.00"))
        op.add_valuation(product=product, amount=Decimal("500.00"), officer=self.officer)
        self.assertEqual(movement_state(product)["value"], Decimal("600.00"))

        op.reverse(officer=self.officer)

        # The valuation row still exists but is excluded via the reversed op.
        self.assertTrue(
            ProductCapitalValuation.objects.filter(operation=op).exists()
        )
        self.assertEqual(capital_delta(product), Decimal("0.00"))
        self.assertEqual(movement_state(product)["value"], Decimal("100.00"))

    def test_reverse_restores_inventory_value(self):
        product = self._make_moved_product(qty=1, price=Decimal("100.00"))

        op = self._make_gain_op(amount=Decimal("500.00"))
        op.add_valuation(product=product, amount=Decimal("500.00"), officer=self.officer)
        self.assertEqual(inventory_value(self.project), Decimal("600.00"))

        op.reverse(officer=self.officer)

        self.assertEqual(inventory_value(self.project), Decimal("100.00"))


class CapitalValuationDetailViewTest(TestCase):
    """The operation detail view renders the capital valuation section."""

    def setUp(self):
        self.officer = make_user()
        self.system = Entity.create(EntityType.SYSTEM)
        self.project = make_project_entity("Farm")
        self.template = make_product_template()

    def test_detail_view_renders_capital_valuation(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_user(
            username="officer_view", password="testpass", is_staff=True
        )
        self.client.login(username="officer_view", password="testpass")

        op = make_operation(
            self.system,
            self.project,
            self.officer,
            CapitalGainOperation,
            OperationType.CAPITAL_GAIN,
            amount=Decimal("500.00"),
        )
        product = make_product(self.template, Decimal("100.00"), 1, self.project)
        op.add_valuation(product=product, amount=Decimal("500.00"), officer=self.officer)

        url = reverse("operation_detail_view", kwargs={"pk": op.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Capital Valuations")
        self.assertContains(response, product.product_template.name)
