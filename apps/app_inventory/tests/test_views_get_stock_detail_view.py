"""GET request tests for app_inventory views.

Tests that ensure authorized users can make GET requests to pages without errors.
"""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import ProductTemplate
from apps.app_inventory.tests.general import (
    make_product_template,
    make_user,
)


class StockDetailViewTest(TestCase):
    """Test GET request to stock detail view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_stock", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm")

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

    def test_reversed_birth_product_not_in_live_stock(self):
        """After a BIRTH is reversed, the born product leaves the live stock tab."""
        from datetime import date
        from decimal import Decimal

        from apps.app_inventory.models import Product, ProductTemplate
        from apps.app_operation.models.operation_type import OperationType
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
        response = self.client.get(url, {"tab": "live"})
        self.assertIn(product, response.context["products"])

        op.reverse(officer=self.officer, reason="test reversal")

        response = self.client.get(url, {"tab": "live"})
        self.assertNotIn(product, response.context["products"])
        self.assertEqual(product.status, Product.Status.REMOVED)

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
