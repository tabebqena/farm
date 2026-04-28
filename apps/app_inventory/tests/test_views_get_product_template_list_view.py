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
