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


class ProductTemplateListViewTest(TestCase):
    """Test GET request to product templates list view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_templates", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm")
        self.template = make_product_template("Calves")
        # Assign template to entity
        self.template.entities.add(self.entity)

    def test_authorized_user_can_load_product_templates_list(self):
        """Test that logged-in user can view product templates list."""
        self.client.login(username="officer_templates", password="testpass")
        url = reverse(
            "entity_product_templates_list", kwargs={"entity_pk": self.entity.pk}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("templates", response.context)

    def test_product_templates_list_displays_templates(self):
        """Test that templates list shows available templates."""
        self.client.login(username="officer_templates", password="testpass")
        url = reverse(
            "entity_product_templates_list", kwargs={"entity_pk": self.entity.pk}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.context["templates"]), 0)

    def test_nonexistent_entity_templates_returns_404(self):
        """Test that requesting templates for non-existent entity returns 404."""
        self.client.login(username="officer_templates", password="testpass")
        url = reverse("entity_product_templates_list", kwargs={"entity_pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)


class ProductTemplateDetailViewTest(TestCase):
    """Test GET request to product template detail view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_template_detail", is_staff=True)
        self.template = make_product_template("Calves")

    def test_authorized_user_can_load_template_detail(self):
        """Test that logged-in user can view product template detail."""
        self.client.login(username="officer_template_detail", password="testpass")
        url = reverse("product_template_detail", kwargs={"pk": self.template.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("template", response.context)
        self.assertEqual(response.context["template"], self.template)

    def test_template_detail_displays_properties(self):
        """Test that template detail shows template properties."""
        self.client.login(username="officer_template_detail", password="testpass")
        url = reverse("product_template_detail", kwargs={"pk": self.template.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("template", response.context)

    def test_nonexistent_template_returns_404(self):
        """Test that requesting non-existent template returns 404."""
        self.client.login(username="officer_template_detail", password="testpass")
        url = reverse("product_template_detail", kwargs={"pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_redirected_from_template_detail(self):
        """Test that unauthenticated users are redirected from template detail."""
        url = reverse("product_template_detail", kwargs={"pk": self.template.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
