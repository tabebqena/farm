"""Tests for entity list view filters, search, and pagination."""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.tests.general import make_user


class EntityListCombinedFiltersTest(TestCase):
    """Test entity list with multiple filters combined."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_combined", is_staff=True)
        self.person_active = Entity.create(
            EntityType.PERSON, name="Active Vendor", is_vendor=True, active=True
        )
        self.person_inactive = Entity.create(
            EntityType.PERSON, name="Inactive Vendor", is_vendor=True, active=False
        )
        self.project_active = Entity.create(
            EntityType.PROJECT, name="Active Farm", active=True
        )

    def test_filter_by_type_and_activation(self):
        """Test filtering by both type and activation status."""
        self.client.login(username="officer_combined", password="testpass")
        response = self.client.get(
            reverse("entity_list"), {"type": "person", "activation": "active"}
        )

        self.assertEqual(response.status_code, 200)
        entities = list(response.context["entities"])
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].name, "Active Vendor")

    def test_filter_by_type_and_search(self):
        """Test filtering by type and search query."""
        self.client.login(username="officer_combined", password="testpass")
        response = self.client.get(
            reverse("entity_list"), {"type": "person", "q": "Vendor", "activation": "active"}
        )

        self.assertEqual(response.status_code, 200)
        entities = list(response.context["entities"])
        # Only active vendor persons
        self.assertEqual(len(entities), 1)
        self.assertTrue(all(e.entity_type == EntityType.PERSON for e in entities))
        self.assertEqual(entities[0].name, "Active Vendor")

    def test_all_filters_combined(self):
        """Test all four filters together."""
        self.client.login(username="officer_combined", password="testpass")
        response = self.client.get(
            reverse("entity_list"),
            {"type": "person", "deletion": "undeleted", "activation": "active", "q": "Vendor"},
        )

        self.assertEqual(response.status_code, 200)
        entities = list(response.context["entities"])
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].name, "Active Vendor")
