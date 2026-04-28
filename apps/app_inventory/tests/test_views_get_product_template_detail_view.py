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
