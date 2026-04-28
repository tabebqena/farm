"""POST request tests for app_entity views.

Tests verify that:
- Valid forms are accepted and models are updated
- Models are created/updated with correct data
- Redirects occur as expected
- Success messages appear
- Form errors are displayed when validation fails
"""

from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.messages import get_messages

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.tests.general import make_user


class ProjectEditViewTest(TestCase):
    """Test POST request to project edit view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_project", is_staff=True)
        self.project = Entity.create(EntityType.PROJECT, name="Farm Project")

    def test_valid_form_updates_project(self):
        """Test that valid form submission updates project entity."""
        self.client.login(username="officer_project", password="testpass")
        url = reverse("project_edit", kwargs={"pk": self.project.pk})

        response = self.client.post(url, {
            "name": "Updated Project",
            "description": "New scope",
            "is_client": True,
            "is_vendor": False,
            "is_internal": True,
            "active": True,
        })

        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Updated Project")
        self.assertEqual(self.project.description, "New scope")
        self.assertTrue(self.project.is_client)
        self.assertTrue(self.project.is_internal)

    def test_valid_form_redirects_to_detail(self):
        """Test that successful form submission redirects to entity detail."""
        self.client.login(username="officer_project", password="testpass")
        url = reverse("project_edit", kwargs={"pk": self.project.pk})

        response = self.client.post(url, {
            "name": "Updated Project",
            "is_client": False,
            "is_vendor": False,
            "is_internal": False,
            "active": True,
        }, follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("entity_detail", kwargs={"pk": self.project.pk})
        )

    def test_valid_form_displays_success_message(self):
        """Test that successful form submission displays success message."""
        self.client.login(username="officer_project", password="testpass")
        url = reverse("project_edit", kwargs={"pk": self.project.pk})

        response = self.client.post(url, {
            "name": "New Project Name",
            "is_client": False,
            "is_vendor": False,
            "is_internal": False,
            "active": True,
        }, follow=True)

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("updated successfully", str(messages[0]))

    def test_invalid_form_missing_name(self):
        """Test that form submission without name shows validation error."""
        self.client.login(username="officer_project", password="testpass")
        url = reverse("project_edit", kwargs={"pk": self.project.pk})

        response = self.client.post(url, {
            "name": "",
            "is_client": False,
            "is_vendor": False,
            "is_internal": False,
            "active": True,
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)
        self.assertIn("required", str(response.context["form"].errors["name"]))

    def test_invalid_form_duplicate_name(self):
        """Test that form submission with duplicate name shows validation error."""
        # Create another project with different name
        other_project = Entity.create(EntityType.PROJECT, name="Other Project")

        self.client.login(username="officer_project", password="testpass")
        url = reverse("project_edit", kwargs={"pk": self.project.pk})

        response = self.client.post(url, {
            "name": "Other Project",
            "is_client": False,
            "is_vendor": False,
            "is_internal": False,
            "active": True,
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)
        self.assertIn("already exists", str(response.context["form"].errors["name"]))

    def test_project_can_use_own_name(self):
        """Test that project can keep their own name when editing."""
        self.client.login(username="officer_project", password="testpass")
        url = reverse("project_edit", kwargs={"pk": self.project.pk})

        response = self.client.post(url, {
            "name": "Farm Project",  # Same name as current
            "is_client": False,
            "is_vendor": False,
            "is_internal": False,
            "active": True,
        })

        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Farm Project")

    def test_edit_non_project_entity_shows_error(self):
        """Test that editing a non-project entity shows error and redirects."""
        person = Entity.create(EntityType.PERSON, name="Test Person")
        self.client.login(username="officer_project", password="testpass")
        url = reverse("project_edit", kwargs={"pk": person.pk})

        response = self.client.post(url, {
            "name": "New Name",
            "is_client": False,
            "is_vendor": False,
            "is_internal": False,
            "active": True,
        }, follow=True)

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("not a Project" in str(m) for m in messages))

    def test_unauthenticated_user_redirected(self):
        """Test that unauthenticated users are redirected."""
        url = reverse("project_edit", kwargs={"pk": self.project.pk})
        response = self.client.post(url, {
            "name": "New Name",
            "is_client": False,
            "is_vendor": False,
            "is_internal": False,
            "active": True,
        })
        self.assertEqual(response.status_code, 302)

    def test_nonexistent_entity_returns_404(self):
        """Test that POST to non-existent entity returns 404."""
        self.client.login(username="officer_project", password="testpass")
        url = reverse("project_edit", kwargs={"pk": 99999})

        response = self.client.post(url, {
            "name": "New Name",
            "is_client": False,
            "is_vendor": False,
            "is_internal": False,
            "active": True,
        })

        self.assertEqual(response.status_code, 404)
