"""Tests for entity list view filters, search, and pagination."""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.tests.general import make_user


class EntityListSearchTest(TestCase):
    """Test entity list search by name."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_search", is_staff=True)
        self.entity1 = Entity.create(EntityType.PERSON, name="Alice Johnson")
        self.entity2 = Entity.create(EntityType.PERSON, name="Bob Smith")
        self.entity3 = Entity.create(EntityType.PERSON, name="Charlie Johnson")

    def test_search_by_partial_name(self):
        """Test searching with partial name match."""
        self.client.login(username="officer_search", password="testpass")
        response = self.client.get(reverse("entity_list"), {"q": "Johnson"})

        self.assertEqual(response.status_code, 200)
        entities = list(response.context["entities"])
        self.assertEqual(len(entities), 2)
        names = {e.name for e in entities}
        self.assertIn("Alice Johnson", names)
        self.assertIn("Charlie Johnson", names)

    def test_search_case_insensitive(self):
        """Test search is case-insensitive."""
        self.client.login(username="officer_search", password="testpass")
        response = self.client.get(reverse("entity_list"), {"q": "bob"})

        self.assertEqual(response.status_code, 200)
        entities = list(response.context["entities"])
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].name, "Bob Smith")

    def test_search_returns_no_results(self):
        """Test search with no matching results."""
        self.client.login(username="officer_search", password="testpass")
        response = self.client.get(reverse("entity_list"), {"q": "NonExistent"})

        self.assertEqual(response.status_code, 200)
        entities = list(response.context["entities"])
        self.assertEqual(len(entities), 0)
