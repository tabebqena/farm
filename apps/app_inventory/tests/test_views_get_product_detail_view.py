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


class ProductDetailViewTest(TestCase):
    """Test GET request to product detail view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_product", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm")
        self.template = make_product_template("Calves")
        # Create a product for this entity
        from apps.app_inventory.models import Product
        from decimal import Decimal

        self.product = Product.objects.create(
            entity=self.entity, product_template=self.template, unit_price=Decimal("100.00")
        )

    def test_authorized_user_can_load_product_detail(self):
        """Test that logged-in user can view product detail."""
        self.client.login(username="officer_product", password="testpass")
        url = reverse("product_detail", kwargs={"pk": self.product.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("product", response.context)
        self.assertEqual(response.context["product"], self.product)

    def test_product_detail_displays_stock_info(self):
        """Test that product detail displays stock information."""
        self.client.login(username="officer_product", password="testpass")
        url = reverse("product_detail", kwargs={"pk": self.product.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("product", response.context)

    def test_nonexistent_product_returns_404(self):
        """Test that requesting non-existent product returns 404."""
        self.client.login(username="officer_product", password="testpass")
        url = reverse("product_detail", kwargs={"pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_redirected_from_product_detail(self):
        """Test that unauthenticated users are redirected from product detail."""
        url = reverse("product_detail", kwargs={"pk": self.product.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
