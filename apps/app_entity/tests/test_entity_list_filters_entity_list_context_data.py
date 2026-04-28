"""Tests for entity list view filters, search, and pagination."""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.tests.general import make_user


class EntityListContextDataTest(TestCase):
    """Test entity list context variables are correctly set."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_context", is_staff=True)

    def test_context_contains_filter_values(self):
        """Test that context preserves filter parameters."""
        self.client.login(username="officer_context", password="testpass")
        response = self.client.get(
            reverse("entity_list"),
            {"type": "person", "deletion": "deleted", "activation": "inactive"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["type_filter"], "person")
        self.assertEqual(response.context["deletion_filter"], "deleted")
        self.assertEqual(response.context["activation_filter"], "inactive")

    def test_context_contains_search_query(self):
        """Test that context preserves search query."""
        self.client.login(username="officer_context", password="testpass")
        response = self.client.get(reverse("entity_list"), {"q": "test"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["search_query"], "test")
