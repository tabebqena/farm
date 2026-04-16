from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.app_entity.models import Entity, Stakeholder, StakeholderRole
from apps.app_inventory.models import Product
from apps.app_inventory.tests.general import (
    make_entity,
    make_invoice,
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
    DeathOperation,
    PurchaseOperation,
    SaleOperation,
)


class ProductTest(TestCase):
    def setUp(self):
        self.officer = make_user()
        self.system = Entity.create(EntityType.SYSTEM)
        self.vendor = make_entity("Vendor", is_vendor=True)
        self.project = make_project_entity("Farm")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.client = make_entity("Client", is_client=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=self.client,
            active=True,
            role=StakeholderRole.CLIENT,
        )
        self.template = make_product_template()

    def _linked_product(
        self,
        proxy_class,
        op_type,
        source,
        destination,
        qty=Decimal("1"),
        price=Decimal("100.00"),
    ):
        """Create an operation → invoice → item → product chain and return the product."""
        op = make_operation(source, destination, self.officer, proxy_class, op_type)
        item = make_invoice_item(make_invoice(op), self.template, qty, price)
        product = make_product(self.template, price, int(qty))
        product.invoice_items.add(item)
        return product

    # --- status ---

    def test_status_active_no_invoice_items(self):
        product = make_product(self.template)
        self.assertEqual(product.status, Product.Status.ACTIVE)

    def test_status_active_after_purchase(self):
        product = self._linked_product(
            PurchaseOperation, OperationType.PURCHASE, self.project, self.vendor
        )
        self.assertEqual(product.status, Product.Status.ACTIVE)

    def test_status_sold_after_sale(self):
        product = self._linked_product(
            SaleOperation, OperationType.SALE, self.client, self.project
        )
        self.assertEqual(product.status, Product.Status.SOLD)

    def test_status_dead_after_death(self):
        product = self._linked_product(
            DeathOperation, OperationType.DEATH, self.project, self.system
        )
        self.assertEqual(product.status, Product.Status.DEAD)

    def test_status_dead_takes_priority_over_sold(self):
        sale_op = make_operation(
            self.client, self.project, self.officer, SaleOperation, OperationType.SALE
        )
        sale_item = make_invoice_item(make_invoice(sale_op), self.template)

        death_op = make_operation(
            self.project, self.system, self.officer, DeathOperation, OperationType.DEATH
        )
        death_item = make_invoice_item(make_invoice(death_op), self.template)

        product = make_product(self.template)
        product.invoice_items.add(sale_item, death_item)
        self.assertEqual(product.status, Product.Status.DEAD)

    # --- current_value ---

    def test_current_value_base_only(self):
        product = make_product(self.template, Decimal("100.00"), 3)
        self.assertEqual(product.current_value, Decimal("300.00"))

    def test_current_value_adds_capital_gain(self):
        cg_op = make_operation(
            self.system,
            self.project,
            self.officer,
            CapitalGainOperation,
            OperationType.CAPITAL_GAIN,
        )
        item = make_invoice_item(
            make_invoice(cg_op), self.template, Decimal("1"), Decimal("20.00")
        )
        product = make_product(self.template, Decimal("100.00"), 1)
        product.invoice_items.add(item)
        self.assertEqual(product.current_value, Decimal("120.00"))

    def test_current_value_subtracts_capital_loss(self):
        cl_op = make_operation(
            self.project,
            self.system,
            self.officer,
            CapitalLossOperation,
            OperationType.CAPITAL_LOSS,
        )
        item = make_invoice_item(
            make_invoice(cl_op), self.template, Decimal("1"), Decimal("15.00")
        )
        product = make_product(self.template, Decimal("100.00"), 1)
        product.invoice_items.add(item)
        self.assertEqual(product.current_value, Decimal("85.00"))

    def test_current_value_gain_and_loss_combined(self):
        """base + gain - loss are applied together."""
        cg_op = make_operation(
            self.system,
            self.project,
            self.officer,
            CapitalGainOperation,
            OperationType.CAPITAL_GAIN,
        )
        cl_op = make_operation(
            self.project,
            self.system,
            self.officer,
            CapitalLossOperation,
            OperationType.CAPITAL_LOSS,
        )
        gain_item = make_invoice_item(
            make_invoice(cg_op), self.template, Decimal("1"), Decimal("30.00")
        )
        loss_item = make_invoice_item(
            make_invoice(cl_op), self.template, Decimal("1"), Decimal("10.00")
        )
        product = make_product(self.template, Decimal("100.00"), 1)
        product.invoice_items.add(gain_item, loss_item)
        # 100 + 30 - 10 = 120
        self.assertEqual(product.current_value, Decimal("120.00"))

    def test_status_active_after_capital_gain(self):
        """A capital gain item does not change the status to SOLD or DEAD."""
        product = self._linked_product(
            CapitalGainOperation, OperationType.CAPITAL_GAIN, self.system, self.project
        )
        self.assertEqual(product.status, Product.Status.ACTIVE)

    def test_status_active_after_capital_loss(self):
        """A capital loss item does not change the status to SOLD or DEAD."""
        product = self._linked_product(
            CapitalLossOperation, OperationType.CAPITAL_LOSS, self.project, self.system
        )
        self.assertEqual(product.status, Product.Status.ACTIVE)

    # --- validation ---

    def test_clean_negative_unit_price_raises(self):
        product = Product(
            product_template=self.template,
            unit_price=Decimal("-1.00"),
            quantity=1,
        )
        with self.assertRaises(ValidationError):
            product.clean()

    def test_clean_zero_unit_price_raises(self):
        """AmountCleanMixin rejects unit_price=0 (must be > 0)."""
        product = Product(
            product_template=self.template,
            unit_price=Decimal("0.00"),
            quantity=1,
        )
        with self.assertRaises(ValidationError):
            product.clean()

    # --- validate_active ---

    def test_validate_active_passes_for_active_product(self):
        product = make_product(self.template)
        product.validate_active()  # must not raise

    def test_validate_active_raises_for_sold_product(self):
        product = self._linked_product(
            SaleOperation, OperationType.SALE, self.client, self.project
        )
        self.assertEqual(product.status, Product.Status.SOLD)
        with self.assertRaises(ValidationError):
            product.validate_active()

    def test_validate_active_raises_for_dead_product(self):
        product = self._linked_product(
            DeathOperation,
            OperationType.DEATH,
            self.project,
            Entity.objects.get(entity_type="system"),
        )
        self.assertEqual(product.status, Product.Status.DEAD)
        with self.assertRaises(ValidationError):
            product.validate_active()
