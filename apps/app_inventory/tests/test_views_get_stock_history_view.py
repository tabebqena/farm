"""GET request tests for the ``stock_history`` view.

The Stock History page traces physical inventory movements (inbound:
purchase/birth; outbound: sale/death/consumption) for an entity's products,
with direction / operation-type / search / date-range filters.
"""

from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import InventoryMovementLine, Product, ProductTemplate
from apps.app_inventory.tests.general import (
    make_invoice_item,
    make_operation,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation, SaleOperation


class StockHistoryViewTest(TestCase):
    """Test GET request to the stock history view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_history", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm")
        self.template = ProductTemplate.objects.create(
            name="Starter Feed",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
            minimum_quantity=Decimal("1.00"),
        )
        self.template.entities.add(self.entity)

    def _make_purchase_movement(
        self, unique_id=None, qty=Decimal("5.00"), price=Decimal("20.00")
    ):
        """Create a PURCHASE movement line whose product belongs to self.entity."""
        vendor = Entity.create(EntityType.PERSON, name="Vendor", is_vendor=True)
        Stakeholder.objects.create(
            parent=self.entity,
            target=vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        op = make_operation(
            self.entity,
            vendor,
            self.officer,
            PurchaseOperation,
            OperationType.PURCHASE,
            amount=(qty * price).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(op, self.template, qty, price)
        product = Product.objects.create(
            product_template=self.template,
            entity=self.entity,
            unit_price=price,
            quantity=int(qty),
            unique_id=unique_id,
        )
        product.invoice_items.add(item)
        line = InventoryMovementLine.objects.create(
            operation=op,
            invoice_item=item,
            product=product,
            quantity=qty,
            date=date.today(),
            officer=self.officer,
        )
        return op, product, line

    def _make_sale_movement(
        self, unique_id=None, qty=Decimal("3.00"), price=Decimal("30.00")
    ):
        """Create a SALE movement line whose product belongs to self.entity."""
        client = Entity.create(EntityType.PERSON, name="Client", is_client=True)
        Stakeholder.objects.create(
            parent=self.entity,
            target=client,
            active=True,
            role=StakeholderRole.CLIENT,
        )
        op = make_operation(
            client,
            self.entity,
            self.officer,
            SaleOperation,
            OperationType.SALE,
            amount=(qty * price).quantize(Decimal("0.01")),
        )
        item = make_invoice_item(op, self.template, qty, price)
        product = Product.objects.create(
            product_template=self.template,
            entity=self.entity,
            unit_price=price,
            quantity=int(qty),
            unique_id=unique_id,
        )
        product.invoice_items.add(item)
        line = InventoryMovementLine.objects.create(
            operation=op,
            invoice_item=item,
            product=product,
            quantity=qty,
            date=date.today(),
            officer=self.officer,
        )
        return op, product, line

    def _movement_lines(self, response):
        return [m["line"] for m in response.context["movements"]]

    def test_authorized_user_can_load_stock_history(self):
        """Authorized GET returns 200 with movements / page_obj context."""
        self.client.login(username="officer_history", password="testpass")
        response = self.client.get(
            reverse("stock_history", kwargs={"entity_pk": self.entity.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("movements", response.context)
        self.assertIn("page_obj", response.context)
        self.assertIn("paginator", response.context)

    def test_history_shows_inbound_and_outbound_movements(self):
        """Purchase (inbound) and sale (outbound) lines both appear."""
        self.client.login(username="officer_history", password="testpass")
        _, _, purchase_line = self._make_purchase_movement(unique_id="FEED-PURCH")
        _, _, sale_line = self._make_sale_movement(unique_id="FEED-SALE")
        response = self.client.get(
            reverse("stock_history", kwargs={"entity_pk": self.entity.pk})
        )
        self.assertEqual(response.status_code, 200)
        lines = self._movement_lines(response)
        self.assertIn(purchase_line, lines)
        self.assertIn(sale_line, lines)

    def test_history_direction_filter(self):
        """direction=in / direction=out return the correct subset."""
        self.client.login(username="officer_history", password="testpass")
        _, _, purchase_line = self._make_purchase_movement(unique_id="FEED-PURCH")
        _, _, sale_line = self._make_sale_movement(unique_id="FEED-SALE")
        url = reverse("stock_history", kwargs={"entity_pk": self.entity.pk})

        response = self.client.get(url, {"direction": "in"})
        lines = self._movement_lines(response)
        self.assertIn(purchase_line, lines)
        self.assertNotIn(sale_line, lines)

        response = self.client.get(url, {"direction": "out"})
        lines = self._movement_lines(response)
        self.assertIn(sale_line, lines)
        self.assertNotIn(purchase_line, lines)

    def test_history_search_by_product_tag(self):
        """Free-text search by product tag narrows the results."""
        self.client.login(username="officer_history", password="testpass")
        _, _, purchase_line = self._make_purchase_movement(unique_id="FEED-PURCH")
        _, _, sale_line = self._make_sale_movement(unique_id="FEED-SALE")
        url = reverse("stock_history", kwargs={"entity_pk": self.entity.pk})

        response = self.client.get(url, {"q": "FEED-PURCH"})
        lines = self._movement_lines(response)
        self.assertIn(purchase_line, lines)
        self.assertNotIn(sale_line, lines)

    def test_history_op_type_filter(self):
        """Exact operation-type filter returns only matching movements."""
        self.client.login(username="officer_history", password="testpass")
        _, _, purchase_line = self._make_purchase_movement(unique_id="FEED-PURCH")
        _, _, sale_line = self._make_sale_movement(unique_id="FEED-SALE")
        url = reverse("stock_history", kwargs={"entity_pk": self.entity.pk})

        response = self.client.get(url, {"op_type": OperationType.PURCHASE})
        lines = self._movement_lines(response)
        self.assertIn(purchase_line, lines)
        self.assertNotIn(sale_line, lines)

    def test_history_nonexistent_entity_returns_404(self):
        """Non-existent entity → 404."""
        self.client.login(username="officer_history", password="testpass")
        response = self.client.get(
            reverse("stock_history", kwargs={"entity_pk": 99999})
        )
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_redirected_from_history(self):
        """Unauthenticated users are redirected (LoginRequiredMiddleware)."""
        url = reverse("stock_history", kwargs={"entity_pk": self.entity.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
