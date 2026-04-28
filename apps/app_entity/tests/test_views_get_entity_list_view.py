"""GET request tests for app_entity views.

Tests that ensure authorized users can make GET requests to pages without errors.
"""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.tests.general import make_user


class EntityListViewTest(TestCase):
    """Test GET request to entity list view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_list", is_staff=True)
        self.non_staff = make_user(username="regular_user", is_staff=False)

    def test_authorized_user_can_load_entity_list(self):
        """Test that logged-in user can view entity list."""
        Entity.create(EntityType.PERSON, name="Test Person")
        Entity.create(EntityType.PROJECT, name="Test Project")

        self.client.login(username="officer_list", password="testpass")
        response = self.client.get(reverse("entity_list"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("entities", response.context)

    def test_non_staff_can_view_entity_list(self):
        """Test that non-staff users can also view entity list."""
        Entity.create(EntityType.PERSON, name="Test Person")

        self.client.login(username="regular_user", password="testpass")
        response = self.client.get(reverse("entity_list"))

        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_user_redirected_from_entity_list(self):
        """Test that unauthenticated users are redirected from entity list."""
        response = self.client.get(reverse("entity_list"))
        self.assertEqual(response.status_code, 302)
