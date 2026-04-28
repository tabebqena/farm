"""Tests for entity form views (create and edit for persons and projects)."""

from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.messages import get_messages

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import ProductTemplate
from apps.app_inventory.tests.general import make_user
from apps.app_operation.models.period import FinancialPeriod


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
