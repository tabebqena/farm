"""Tests for entity list view filters, search, and pagination."""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.tests.general import make_user


class EntityListFilterByActivationTest(TestCase):
    """Test entity list filtering by active status."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_activation", is_staff=True)
        self.active = Entity.create(EntityType.PERSON, name="Active Person", active=True)
        self.inactive = Entity.create(
            EntityType.PERSON, name="Inactive Person", active=False
        )

    def test_filter_by_activation_active(self):
        """Test filtering to show only active entities."""
        self.client.login(username="officer_activation", password="testpass")
        response = self.client.get(reverse("entity_list"), {"activation": "active"})

        self.assertEqual(response.status_code, 200)
        entities = list(response.context["entities"])
        entity_ids = [e.id for e in entities]
        self.assertIn(self.active.id, entity_ids)
        self.assertNotIn(self.inactive.id, entity_ids)

    def test_filter_by_activation_inactive(self):
        """Test filtering to show only inactive entities."""
        self.client.login(username="officer_activation", password="testpass")
        response = self.client.get(reverse("entity_list"), {"activation": "inactive"})

        self.assertEqual(response.status_code, 200)
        entities = list(response.context["entities"])
        entity_ids = [e.id for e in entities]
        self.assertIn(self.inactive.id, entity_ids)
        self.assertNotIn(self.active.id, entity_ids)
