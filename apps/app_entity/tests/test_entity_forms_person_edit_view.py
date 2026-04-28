"""Tests for entity form views (create and edit for persons and projects)."""

from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.messages import get_messages

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import ProductTemplate
from apps.app_inventory.tests.general import make_user
from apps.app_operation.models.period import FinancialPeriod


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
