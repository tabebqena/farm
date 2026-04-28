"""GET request tests for app_entity views.

Tests that ensure authorized users can make GET requests to pages without errors.
"""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.tests.general import make_user


class EntityDetailViewTest(TestCase):
    """Test GET request to entity detail view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_detail", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Test Project")

    def test_authorized_user_can_load_entity_detail(self):
        """Test that logged-in user can view entity detail."""
        self.client.login(username="officer_detail", password="testpass")
        url = reverse("entity_detail", kwargs={"pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("entity", response.context)
        self.assertEqual(response.context["entity"], self.entity)

    def test_entity_detail_with_stakeholders(self):
        """Test entity detail view loads with stakeholders."""
        vendor = Entity.create(EntityType.PERSON, name="Vendor")
        Stakeholder.objects.create(
            parent=self.entity,
            target=vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )

        self.client.login(username="officer_detail", password="testpass")
        url = reverse("entity_detail", kwargs={"pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("entity", response.context)

    def test_nonexistent_entity_detail_returns_404(self):
        """Test that requesting non-existent entity returns 404."""
        self.client.login(username="officer_detail", password="testpass")
        url = reverse("entity_detail", kwargs={"pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_redirected_from_entity_detail(self):
        """Test that unauthenticated users are redirected from entity detail."""
        url = reverse("entity_detail", kwargs={"pk": self.entity.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
