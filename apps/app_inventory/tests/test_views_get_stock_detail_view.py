"""GET request tests for app_inventory views.

Tests that ensure authorized users can make GET requests to pages without errors.
"""

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
    make_invoice_item,
    make_operation,
    make_product_template,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation, SaleOperation


class StockDetailViewTest(TestCase):
    """Test GET request to stock detail view."""

    _vendor_seq = 0

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_stock", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm")

    def _make_present_product(
        self, template, unique_id=None, qty=Decimal("5.00"), price=Decimal("20.00")
    ):
        """Create a physically present product (purchased + moved) for self.entity."""
        StockDetailViewTest._vendor_seq += 1
        vendor = Entity.create(
            EntityType.PERSON,
            name=f"Vendor-{StockDetailViewTest._vendor_seq}",
            is_vendor=True,
        )
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
        item = make_invoice_item(op, template, qty, price)
        product = Product.objects.create(
            product_template=template,
            entity=self.entity,
            unit_price=price,
            quantity=int(qty),
            unique_id=unique_id,
        )
        product.invoice_items.add(item)
        InventoryMovementLine.objects.create(
            operation=op,
            invoice_item=item,
            product=product,
            quantity=qty,
            date=date.today(),
            officer=self.officer,
        )
        return product

    def test_authorized_user_can_load_stock_detail(self):
        """Test that logged-in user can view stock detail."""
        self.client.login(username="officer_stock", password="testpass")
        url = reverse("stock_detail", kwargs={"entity_pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("entity", response.context)

    def test_stock_detail_with_products(self):
        """Test that stock detail view loads with products."""
        self.client.login(username="officer_stock", password="testpass")
        url = reverse("stock_detail", kwargs={"entity_pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("entity", response.context)

    def test_internal_client_receipt_appears_in_buyer_stock(self):
        """An internal-client sale puts the received product into the buyer's
        live stock (direction-aware stock_detail)."""
        self.client.login(username="officer_stock", password="testpass")
        template = ProductTemplate.objects.create(
            name="Feed",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            tracking_mode=ProductTemplate.TrackingMode.COMMODITY,
            default_unit="Kg",
            minimum_quantity=Decimal("0.01"),
        )
        template.entities.add(self.entity)
        seller_product = self._make_present_product(template, qty=Decimal("4.00"))

        internal_client = Entity.create(
            EntityType.PERSON,
            name="Internal Buyer",
            is_client=True,
            is_internal=True,
            active=True,
        )
        Stakeholder.objects.create(
            parent=self.entity,
            target=internal_client,
            role=StakeholderRole.CLIENT,
            active=True,
        )
        SaleOperation.create_from_session(
            project=self.entity,
            session_data={
                "date": date.today().isoformat(),
                "client_id": internal_client.pk,
                "description": "Transfer",
                "total_amount": "400.00",
                "amount_paid": "0",
                "items": [
                    {
                        "product_id": seller_product.pk,
                        "description": "",
                        "quantity": "4.00",
                        "unit_price": "100.00",
                    }
                ],
            },
            officer=self.officer,
        )

        url = reverse("stock_detail", kwargs={"entity_pk": internal_client.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        present_ids = [
            row["product"].pk
            for row in response.context["physically_present_products"]
        ]
        buyer_clone = Product.objects.get(
            entity=internal_client, product_template=template
        )
        self.assertIn(buyer_clone.pk, present_ids)

    def test_reversed_birth_product_not_in_live_stock(self):
        """After a BIRTH is reversed, the born product leaves the live stock.

        No ``?tab=live`` is required anymore — live (physically present) is the
        default and only view.
        """
        from apps.app_operation.models.proxies import BirthOperation

        # A birth's source is the System entity; the newborn belongs to the
        # project (destination), so it appears in the project's stock live tab.
        system = Entity.create(EntityType.SYSTEM)
        template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
        )
        template.entities.add(self.entity)

        raw_post = {
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": "",
            "items-0-product_template": str(template.pk),
            "items-0-quantity": "1",
            "items-0-unit_price": "100.00",
            "items-0-description": "",
            "items-0-unique_id": "",
            "items-0-DELETE": "",
        }
        op = BirthOperation.create(
            operation_type=OperationType.BIRTH,
            source=system,
            destination=self.entity,
            amount=Decimal("100.00"),
            date=date.today(),
            description="Test birth",
            officer=self.officer,
            amount_paid=Decimal("0.00"),
            raw_post=raw_post,
            project=self.entity,
        )
        product = op.movement_lines.first().product
        self.assertEqual(product.entity_id, self.entity.pk)

        self.client.login(username="officer_stock", password="testpass")
        url = reverse("stock_detail", kwargs={"entity_pk": self.entity.pk})
        response = self.client.get(url)
        self.assertIn(product, response.context["products"])

        op.reverse(officer=self.officer, reason="test reversal")

        response = self.client.get(url)
        self.assertNotIn(product, response.context["products"])
        self.assertEqual(product.status, Product.Status.REMOVED)

    def test_stock_detail_has_pagination_and_search_context(self):
        """The reworked page exposes pagination and per-product card context."""
        self.client.login(username="officer_stock", password="testpass")
        url = reverse("stock_detail", kwargs={"entity_pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("page_obj", response.context)
        self.assertIn("paginator", response.context)
        self.assertIn("physically_present_products", response.context)
        self.assertIn("search_query", response.context)
        self.assertIn("obligated_outbound_qty", response.context)

    def test_physically_present_animal_renders_own_card(self):
        """An individually-tracked animal gets its own card with its tag/ID."""
        template = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
        )
        template.entities.add(self.entity)
        product = self._make_present_product(
            template, unique_id="CALF-001", qty=Decimal("1.00"), price=Decimal("100.00")
        )

        self.client.login(username="officer_stock", password="testpass")
        response = self.client.get(
            reverse("stock_detail", kwargs={"entity_pk": self.entity.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CALF-001")
        entries = response.context["physically_present_products"]
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["is_animal"])
        self.assertEqual(entries[0]["product"].pk, product.pk)

    def test_physically_present_commodity_renders_quantity_and_unit(self):
        """A commodity product card shows its ledger quantity and unit."""
        template = ProductTemplate.objects.create(
            name="Starter Feed",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
            minimum_quantity=Decimal("1.00"),
        )
        template.entities.add(self.entity)
        self._make_present_product(template, unique_id="FEED-001")

        self.client.login(username="officer_stock", password="testpass")
        response = self.client.get(
            reverse("stock_detail", kwargs={"entity_pk": self.entity.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Starter Feed")
        self.assertContains(response, "Kg")
        entries = response.context["physically_present_products"]
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]["is_animal"])
        self.assertEqual(entries[0]["quantity"], Decimal("5.00"))

    def test_stock_detail_search_filters_products(self):
        """Searching by tag narrows the physically present products."""
        animal = ProductTemplate.objects.create(
            name="Calves",
            nature=ProductTemplate.Nature.ANIMAL,
            sub_category="Cattle",
            tracking_mode=ProductTemplate.TrackingMode.INDIVIDUAL,
            default_unit="Head",
        )
        animal.entities.add(self.entity)
        feed = ProductTemplate.objects.create(
            name="Starter Feed",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
            minimum_quantity=Decimal("1.00"),
        )
        feed.entities.add(self.entity)
        animal_product = self._make_present_product(
            animal, unique_id="CALF-001", qty=Decimal("1.00")
        )
        feed_product = self._make_present_product(feed, unique_id="FEED-001")

        self.client.login(username="officer_stock", password="testpass")
        url = reverse("stock_detail", kwargs={"entity_pk": self.entity.pk})
        response = self.client.get(url, {"q": "CALF"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["search_query"], "CALF")
        product_ids = [p.pk for p in response.context["products"]]
        self.assertIn(animal_product.pk, product_ids)
        self.assertNotIn(feed_product.pk, product_ids)

    def test_obligated_inbound_text_not_shown(self):
        """Obligated Inbound is not physically present — it never appears."""
        # Create an inbound obligation (purchase issued but not yet moved).
        template = ProductTemplate.objects.create(
            name="Starter Feed",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
            minimum_quantity=Decimal("1.00"),
        )
        template.entities.add(self.entity)
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
            amount=Decimal("100.00"),
        )
        make_invoice_item(op, template, Decimal("5.00"), Decimal("20.00"))
        # The unpaid purchase is an obligation without movement.

        self.client.login(username="officer_stock", password="testpass")
        response = self.client.get(
            reverse("stock_detail", kwargs={"entity_pk": self.entity.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Obligated Inbound")

    def test_obligated_outbound_warning_appears_when_present(self):
        """The Obligated Outbound warning renders only when there is an
        obligation."""
        client = Entity.create(EntityType.PERSON, name="Client", is_client=True)
        Stakeholder.objects.create(
            parent=self.entity,
            target=client,
            active=True,
            role=StakeholderRole.CLIENT,
        )
        template = ProductTemplate.objects.create(
            name="Starter Feed",
            nature=ProductTemplate.Nature.FEED,
            sub_category="Feed",
            default_unit="Kg",
            minimum_quantity=Decimal("1.00"),
        )
        template.entities.add(self.entity)
        op = make_operation(
            client,
            self.entity,
            self.officer,
            SaleOperation,
            OperationType.SALE,
            amount=Decimal("100.00"),
        )
        make_invoice_item(op, template, Decimal("5.00"), Decimal("20.00"))
        # The sale is an outbound obligation without movement.

        self.client.login(username="officer_stock", password="testpass")
        response = self.client.get(
            reverse("stock_detail", kwargs={"entity_pk": self.entity.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "committed for outbound delivery")

    def test_obligated_outbound_warning_absent_when_no_obligation(self):
        """No warning when there is no obligated outbound."""
        self.client.login(username="officer_stock", password="testpass")
        response = self.client.get(
            reverse("stock_detail", kwargs={"entity_pk": self.entity.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "committed for outbound delivery")

    def test_nonexistent_entity_stock_returns_404(self):
        """Test that requesting stock for non-existent entity returns 404."""
        self.client.login(username="officer_stock", password="testpass")
        url = reverse("stock_detail", kwargs={"entity_pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_redirected_from_stock(self):
        """Test that unauthenticated users are redirected from stock detail."""
        url = reverse("stock_detail", kwargs={"entity_pk": self.entity.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
