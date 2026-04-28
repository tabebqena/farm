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
