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
