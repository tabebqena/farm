"""Stock query tests for ``apps.app_inventory.stock`` — the movement-based
replacement for the removed ``ProductLedgerEntry`` table.

The stock module answers "what's physically available (qty, value)" and
"what's inbound / outbound" directly from ``InventoryMovementLine`` (the
physical events) plus ``InvoiceItem`` (contract obligations and capital).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import InventoryMovementLine, ProductTemplate
from apps.app_inventory.stock import (
    inventory_value,
    movement_state,
    pending_items,
    portfolio,
)
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
    ConsumptionOperation,
    PurchaseOperation,
    SaleOperation,
)


def _feed_template(name="Feed Mix"):
    return ProductTemplate.objects.create(
        name=name,
        nature=ProductTemplate.Nature.FEED,
        sub_category="Feed",
        default_unit="Kg",
        minimum_quantity=Decimal("1.00"),
    )


class StockMovementStateTest(TestCase):
    """movement_state() — net physical presence derived from movement lines."""

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
        self.client = make_entity(EntityType.PERSON, "Client", is_client=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=self.client,
            active=True,
            role=StakeholderRole.CLIENT,
        )
        self.template = make_product_template()
        self.template.entities.add(self.project)
        self.product = make_product(self.template, entity=self.project)

    def _movement(
        self,
        product,
        proxy_class,
        op_type,
        source,
        destination,
        qty,
        price,
        when=None,
    ):
        """Create an op + invoice item + movement line for *product*."""
        op = make_operation(
            source,
            destination,
            self.officer,
            proxy_class,
            op_type,
            amount=(qty * price).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(op, product.product_template, qty, price)
        InventoryMovementLine.objects.create(
            operation=op,
            invoice_item=item,
            product=product,
            quantity=qty,
            date=when or date.today(),
            officer=self.officer,
        )
        return op, item

    def test_state_zeros_without_movements(self):
        state = movement_state(self.product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("0.00"))
        self.assertEqual(state["value"], Decimal("0.00"))

    def test_consumption_valued_at_purchase_price(self):
        """100 kg @ $2 then consume 30 kg leaves 70 kg / $140."""
        feed = _feed_template()
        feed.entities.add(self.project)
        product = make_product(feed, Decimal("2.00"), 100, entity=self.project)
        self._movement(
            product, PurchaseOperation, OperationType.PURCHASE,
            self.project, self.vendor, Decimal("100.00"), Decimal("2.00"),
        )
        self._movement(
            product, ConsumptionOperation, OperationType.CONSUMPTION,
            self.project, self.system, Decimal("30.00"), Decimal("2.00"),
        )
        state = movement_state(product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("70.00"))
        self.assertEqual(state["value"], Decimal("140.00"))

    def test_state_as_of_before_movement_is_zero(self):
        """A movement dated today must not count for an as_of of yesterday."""
        self._movement(
            self.product, PurchaseOperation, OperationType.PURCHASE,
            self.project, self.vendor, Decimal("10.00"), Decimal("50.00"),
        )
        state = movement_state(self.product, as_of=date.today() - timedelta(days=1))
        self.assertEqual(state["quantity"], Decimal("0.00"))

    def test_reversed_movement_is_excluded(self):
        """A reversed receipt nets back to zero (the reversal line and its
        reversed original are both excluded from the stock queries)."""
        op, _item = self._movement(
            self.product, PurchaseOperation, OperationType.PURCHASE,
            self.project, self.vendor, Decimal("10.00"), Decimal("50.00"),
        )
        op.movement_lines.first().reverse(self.officer)
        state = movement_state(self.product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("0.00"))
        self.assertEqual(state["value"], Decimal("0.00"))

    def test_sale_dispatch_reduces_seller_stock(self):
        """A sale dispatches goods from the seller's stock (net −)."""
        self._movement(
            self.product, PurchaseOperation, OperationType.PURCHASE,
            self.project, self.vendor, Decimal("10.00"), Decimal("50.00"),
        )
        self._movement(
            self.product, SaleOperation, OperationType.SALE,
            self.client, self.project, Decimal("4.00"), Decimal("80.00"),
        )
        state = movement_state(self.product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("6.00"))

    def test_sale_buyer_receipt_increases_buyer_stock(self):
        """An internal-client sale gives the buyer's copy a net + receipt."""
        buyer_product = make_product(self.template, entity=self.client, quantity=1)
        self._movement(
            buyer_product, SaleOperation, OperationType.SALE,
            self.client, self.project, Decimal("4.00"), Decimal("80.00"),
        )
        state = movement_state(buyer_product, as_of=date.today())
        self.assertEqual(state["quantity"], Decimal("4.00"))


class StockPortfolioTest(TestCase):
    """portfolio() / inventory_value() — physical availability per entity."""

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
        self.client = make_entity(EntityType.PERSON, "Client", is_client=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=self.client,
            active=True,
            role=StakeholderRole.CLIENT,
        )
        self.template = make_product_template()
        self.template.entities.add(self.project)
        self.feed = _feed_template("Feed Mix")
        self.feed.entities.add(self.project)
        self.other_template = make_product_template("Sheep")
        self.other_template.entities.add(self.project)

    def _receive(self, product, qty, price):
        op = make_operation(
            self.project,
            self.vendor,
            self.officer,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=(qty * price).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(op, product.product_template, qty, price)
        InventoryMovementLine.objects.create(
            operation=op,
            invoice_item=item,
            product=product,
            quantity=qty,
            date=date.today(),
            officer=self.officer,
        )
        return product

    def test_portfolio_excludes_zero_quantity_products(self):
        """Only products with a positive net presence appear in the portfolio."""
        received = self._receive(
            make_product(self.other_template, Decimal("80.00"), 3, self.project),
            Decimal("3.00"),
            Decimal("80.00"),
        )
        unmoved = make_product(self.template, Decimal("100.00"), 5, self.project)
        rows = portfolio(self.project, as_of=date.today())
        product_ids = {row["product_id"] for row in rows}
        self.assertIn(received.pk, product_ids)
        self.assertNotIn(unmoved.pk, product_ids)

    def test_portfolio_and_value_after_death_consumption_sale(self):
        """Written-off stock nets to zero; only on-hand stock remains in the
        portfolio and in the inventory value."""
        dead = self._receive(
            make_product(self.template, Decimal("100.00"), 10, self.project),
            Decimal("10.00"),
            Decimal("100.00"),
        )
        consumed = self._receive(
            make_product(self.feed, Decimal("200.00"), 5, self.project),
            Decimal("5.00"),
            Decimal("200.00"),
        )
        sold = self._receive(
            make_product(self.other_template, Decimal("50.00"), 3, self.project),
            Decimal("3.00"),
            Decimal("50.00"),
        )
        available = self._receive(
            make_product(self.other_template, Decimal("25.00"), 7, self.project),
            Decimal("7.00"),
            Decimal("25.00"),
        )

        # Outbound events — the project writes stock off to the system.
        def _outbound(product, proxy, op_type, qty, source, destination):
            op = make_operation(
                source,
                destination,
                self.officer,
                proxy,
                op_type,
                amount=(qty * product.unit_price).quantize(Decimal("0.01")),
            )
            item = make_invoice_item(op, product.product_template, qty, product.unit_price)
            InventoryMovementLine.objects.create(
                operation=op,
                invoice_item=item,
                product=product,
                quantity=qty,
                date=date.today(),
                officer=self.officer,
            )

        from apps.app_operation.models.proxies import DeathOperation

        _outbound(dead, DeathOperation, OperationType.DEATH, Decimal("10.00"), self.project, self.system)
        _outbound(consumed, ConsumptionOperation, OperationType.CONSUMPTION, Decimal("5.00"), self.project, self.system)
        _outbound(sold, SaleOperation, OperationType.SALE, Decimal("3.00"), self.client, self.project)

        rows = portfolio(self.project, as_of=date.today())
        product_ids = {row["product_id"] for row in rows}
        self.assertIn(available.pk, product_ids)
        self.assertNotIn(dead.pk, product_ids)
        self.assertNotIn(consumed.pk, product_ids)
        self.assertNotIn(sold.pk, product_ids)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["quantity"], Decimal("7.00"))
        self.assertEqual(rows[0]["value"], Decimal("175.00"))
        self.assertEqual(inventory_value(self.project, as_of=date.today()), Decimal("175.00"))


class StockPendingItemsTest(TestCase):
    """pending_items() — inbound / outbound contract obligations."""

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
        self.client = make_entity(EntityType.PERSON, "Client", is_client=True)
        Stakeholder.objects.create(
            parent=self.project,
            target=self.client,
            active=True,
            role=StakeholderRole.CLIENT,
        )
        self.template = make_product_template()
        self.template.entities.add(self.project)

    def test_pending_inbound_for_unreceived_purchase(self):
        op = make_operation(
            self.project,
            self.vendor,
            self.officer,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=Decimal("500.00"),
        )
        item = make_invoice_item(op, self.template, Decimal("5.00"), Decimal("100.00"))
        rows = pending_items(entity=self.project, as_of=date.today())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], item.pk)
        self.assertEqual(rows[0]["issued_qty"], Decimal("5.00"))
        self.assertEqual(rows[0]["pending_qty"], Decimal("5.00"))

    def test_no_pending_for_received_purchase(self):
        op = make_operation(
            self.project,
            self.vendor,
            self.officer,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=Decimal("500.00"),
        )
        item = make_invoice_item(op, self.template, Decimal("5.00"), Decimal("100.00"))
        product = make_product(self.template, entity=self.project, quantity=5)
        InventoryMovementLine.objects.create(
            operation=op,
            invoice_item=item,
            product=product,
            quantity=Decimal("5.00"),
            date=date.today(),
            officer=self.officer,
        )
        self.assertEqual(pending_items(entity=self.project, as_of=date.today()), [])

    def test_pending_outbound_for_undelivered_sale(self):
        op = make_operation(
            self.client,
            self.project,
            self.officer,
            SaleOperation,
            OperationType.SALE,
            amount=Decimal("500.00"),
        )
        make_invoice_item(op, self.template, Decimal("5.00"), Decimal("100.00"))
        rows = pending_items(entity=self.project, as_of=date.today())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["issued_qty"], Decimal("-5.00"))
        self.assertEqual(rows[0]["pending_qty"], Decimal("-5.00"))
