from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import (
    InventoryMovementLine,
    Product,
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


class ConsumptionStockDetailTest(TestCase):
    """The stock-detail 'consumed' tab shows consumed products once movement
    lines are auto-created on consumption."""

    def setUp(self):
        self.client = Client()
        self.system_entity = Entity.create(EntityType.SYSTEM)
        self.officer_user = make_user(username="officer_stock")
        self.project_entity = make_project_entity("Test Farm Project")
        self.vendor = make_entity(EntityType.PERSON, "Vendor", is_vendor=True)
        Stakeholder.objects.create(
            parent=self.project_entity,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        self.template = ProductTemplate.objects.create(
            name="Feed Mix",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
        )

    def _make_moved_product(self, qty=Decimal("5.00"), price=Decimal("100.00")):
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

    def test_consumed_product_movement_in_stock_history(self):
        """The consumed product leaves stock detail but its OUT movement shows
        up on the Stock History page (tabs were dropped in the rework)."""
        product = self._make_moved_product()
        consumption = self._consume(product)
        consumption_line = consumption.movement_lines.first()
        self.assertIsNotNone(consumption_line)

        self.client.login(username="officer_stock", password="testpass")
        url = reverse("stock_history", kwargs={"entity_pk": self.project_entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        lines = [m["line"] for m in response.context["movements"]]
        self.assertIn(consumption_line, lines)
        self.assertEqual(
            Product.objects.get(pk=product.pk).status, Product.Status.CONSUMED
        )

    def test_live_stock_excludes_consumed_product(self):
        product = self._make_moved_product()
        self._consume(product)

        self.client.login(username="officer_stock", password="testpass")
        url = reverse("stock_detail", kwargs={"entity_pk": self.project_entity.pk})
        response = self.client.get(url, {"tab": "live"})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(product, response.context["products"])
