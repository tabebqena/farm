"""Tests for entity form views (create and edit for persons and projects)."""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import ProductTemplate
from apps.app_inventory.tests.general import make_user


class PersonCreateViewTest(TestCase):
    """Test person creation view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_person", is_staff=True)

    def test_person_create_get_renders_form(self):
        """Test GET request to person_create shows form."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.get(reverse("person_create"))

        self.assertEqual(response.status_code, 200)

    def test_person_create_post_creates_entity(self):
        """Test POST creates a new person entity."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "John Doe",
                "private_description": "A test person",
                "is_vendor": "on",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
            },
        )

        # Should redirect to entity detail
        self.assertEqual(response.status_code, 302)
        # Verify entity was created
        self.assertTrue(Entity.objects.filter(name="John Doe").exists())
        entity = Entity.objects.get(name="John Doe")
        self.assertEqual(entity.entity_type, EntityType.PERSON)
        self.assertTrue(entity.is_vendor)
        self.assertFalse(entity.is_worker)

    def test_person_create_with_all_roles(self):
        """Test creating person with multiple roles."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Multi-Role Person",
                "private_description": "Wears many hats",
                "is_vendor": "on",
                "is_worker": "on",
                "is_client": "on",
                "is_shareholder": "on",
                "is_internal": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        entity = Entity.objects.get(name="Multi-Role Person")
        self.assertTrue(entity.is_vendor)
        self.assertTrue(entity.is_worker)
        self.assertTrue(entity.is_client)
        self.assertTrue(entity.is_shareholder)
        self.assertTrue(entity.is_internal)

    def test_person_create_with_no_roles(self):
        """Test creating person with no roles."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Generic Person",
                "private_description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        entity = Entity.objects.get(name="Generic Person")
        self.assertFalse(entity.is_vendor)
        self.assertFalse(entity.is_worker)

    def test_person_create_with_description(self):
        """Test person creation includes private description."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Described Person",
                "private_description": "This is a detailed description",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        entity = Entity.objects.get(name="Described Person")
        self.assertEqual(entity.description, "This is a detailed description")

    def test_person_create_redirects_to_detail(self):
        """Test successful person creation redirects to entity detail."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Redirect Test",
                "private_description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
            },
            follow=True,
        )

        entity = Entity.objects.get(name="Redirect Test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Redirect Test")


class PersonEditViewTest(TestCase):
    """Test person edit view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_edit", is_staff=True)
        self.person = Entity.create(
            EntityType.PERSON, name="Original Name", is_vendor=True, is_worker=False
        )

    def test_person_edit_get_renders_form(self):
        """Test GET request to person_edit shows form with current data."""
        self.client.login(username="officer_edit", password="testpass")
        response = self.client.get(reverse("person_edit", kwargs={"pk": self.person.pk}))

        self.assertEqual(response.status_code, 200)

    def test_person_edit_post_updates_name(self):
        """Test POST updates person name."""
        self.client.login(username="officer_edit", password="testpass")
        response = self.client.post(
            reverse("person_edit", kwargs={"pk": self.person.pk}),
            {
                "name": "Updated Name",
                "private_description": "Updated description",
                "is_vendor": "on",
                "is_worker": "on",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.person.refresh_from_db()
        self.assertEqual(self.person.name, "Updated Name")

    def test_person_edit_updates_roles(self):
        """Test POST updates person roles."""
        self.client.login(username="officer_edit", password="testpass")
        self.assertFalse(self.person.is_worker)

        response = self.client.post(
            reverse("person_edit", kwargs={"pk": self.person.pk}),
            {
                "name": "Original Name",
                "private_description": "",
                "is_vendor": "on",
                "is_worker": "on",
                "is_client": "on",
                "is_shareholder": "",
                "is_internal": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.person.refresh_from_db()
        self.assertTrue(self.person.is_worker)
        self.assertTrue(self.person.is_client)

    def test_person_edit_removes_roles(self):
        """Test POST can remove roles."""
        self.client.login(username="officer_edit", password="testpass")
        self.assertTrue(self.person.is_vendor)

        response = self.client.post(
            reverse("person_edit", kwargs={"pk": self.person.pk}),
            {
                "name": "Original Name",
                "private_description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.person.refresh_from_db()
        self.assertFalse(self.person.is_vendor)

    def test_person_edit_nonexistent_returns_404(self):
        """Test editing non-existent person returns 404."""
        self.client.login(username="officer_edit", password="testpass")
        response = self.client.get(reverse("person_edit", kwargs={"pk": 99999}))

        self.assertEqual(response.status_code, 404)


class ProjectEditViewTest(TestCase):
    """Test project edit view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_proj_edit", is_staff=True)
        self.project = Entity.create(
            EntityType.PROJECT, name="Original Project", is_client=False
        )

    def test_project_edit_get_renders_form(self):
        """Test GET request to project_edit shows form."""
        self.client.login(username="officer_proj_edit", password="testpass")
        response = self.client.get(reverse("project_edit", kwargs={"pk": self.project.pk}))

        self.assertEqual(response.status_code, 200)

    def test_project_edit_post_updates_name(self):
        """Test POST updates project name."""
        self.client.login(username="officer_proj_edit", password="testpass")
        response = self.client.post(
            reverse("project_edit", kwargs={"pk": self.project.pk}),
            {
                "name": "Updated Project",
                "description": "Updated description",
                "end_date": "",
                "is_vendor": "",
                "is_client": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Updated Project")

    def test_project_edit_updates_description(self):
        """Test POST updates project description."""
        self.client.login(username="officer_proj_edit", password="testpass")
        response = self.client.post(
            reverse("project_edit", kwargs={"pk": self.project.pk}),
            {
                "name": "Original Project",
                "description": "Updated description",
                "end_date": "",
                "is_vendor": "",
                "is_client": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.description, "Updated description")

    def test_project_edit_nonexistent_returns_404(self):
        """Test editing non-existent project returns 404."""
        self.client.login(username="officer_proj_edit", password="testpass")
        response = self.client.get(reverse("project_edit", kwargs={"pk": 99999}))

        self.assertEqual(response.status_code, 404)


