"""Tests for entity list view filters, search, and pagination."""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.tests.general import make_user


class EntityListFilterByTypeTest(TestCase):
    """Test entity list filtering by type parameter."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_filter", is_staff=True)
        self.person1 = Entity.create(EntityType.PERSON, name="Alice")
        self.person2 = Entity.create(EntityType.PERSON, name="Bob")
        self.project1 = Entity.create(EntityType.PROJECT, name="Farm A")
        self.project2 = Entity.create(EntityType.PROJECT, name="Farm B")

    def test_filter_by_type_person(self):
        """Test filtering to show only PERSON entities."""
        self.client.login(username="officer_filter", password="testpass")
        response = self.client.get(reverse("entity_list"), {"type": "person"})

        self.assertEqual(response.status_code, 200)
        entities = list(response.context["entities"])
        self.assertEqual(len(entities), 2)
        self.assertTrue(all(e.entity_type == EntityType.PERSON for e in entities))

    def test_filter_by_type_project(self):
        """Test filtering to show only PROJECT entities."""
        self.client.login(username="officer_filter", password="testpass")
        response = self.client.get(reverse("entity_list"), {"type": "project"})

        self.assertEqual(response.status_code, 200)
        entities = list(response.context["entities"])
        self.assertEqual(len(entities), 2)
        self.assertTrue(all(e.entity_type == EntityType.PROJECT for e in entities))

    def test_filter_by_type_all_excludes_system_world(self):
        """Test default 'all' filter excludes SYSTEM and WORLD types."""
        Entity.create(EntityType.SYSTEM)
        Entity.create(EntityType.WORLD)

        self.client.login(username="officer_filter", password="testpass")
        response = self.client.get(reverse("entity_list"), {"type": "all"})

        self.assertEqual(response.status_code, 200)
        entities = list(response.context["entities"])
        # Should have persons and projects but not SYSTEM/WORLD
        entity_types = [e.entity_type for e in entities]
        self.assertNotIn(EntityType.SYSTEM, entity_types)
        self.assertNotIn(EntityType.WORLD, entity_types)

    def test_filter_by_type_system_world(self):
        """Test filtering to show only SYSTEM and WORLD entities."""
        system = Entity.create(EntityType.SYSTEM)
        world = Entity.create(EntityType.WORLD)

        self.client.login(username="officer_filter", password="testpass")
        response = self.client.get(reverse("entity_list"), {"type": "system_world"})

        self.assertEqual(response.status_code, 200)
        entities = list(response.context["entities"])
        self.assertEqual(len(entities), 2)
        entity_types = {e.entity_type for e in entities}
        self.assertIn(EntityType.SYSTEM, entity_types)
        self.assertIn(EntityType.WORLD, entity_types)
