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


class PersonEditViewTest(TestCase):
    """Test POST request to person edit view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_edit", is_staff=True)
        self.person = Entity.create(EntityType.PERSON, name="John Doe")

    def test_valid_form_updates_person(self):
        """Test that valid form submission updates person entity."""
        self.client.login(username="officer_edit", password="testpass")
        url = reverse("person_edit", kwargs={"pk": self.person.pk})

        response = self.client.post(url, {
            "name": "Jane Doe",
            "description": "Updated description",
            "is_worker": True,
            "is_vendor": False,
            "is_client": True,
            "is_shareholder": False,
            "is_internal": False,
            "active": True,
        })

        self.person.refresh_from_db()
        self.assertEqual(self.person.name, "Jane Doe")
        self.assertEqual(self.person.description, "Updated description")
        self.assertTrue(self.person.is_worker)
        self.assertTrue(self.person.is_client)

    def test_valid_form_redirects_to_detail(self):
        """Test that successful form submission redirects to entity detail."""
        self.client.login(username="officer_edit", password="testpass")
        url = reverse("person_edit", kwargs={"pk": self.person.pk})

        response = self.client.post(url, {
            "name": "Updated Name",
            "is_worker": False,
            "is_vendor": False,
            "is_client": False,
            "is_shareholder": False,
            "is_internal": False,
            "active": True,
        }, follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("entity_detail", kwargs={"pk": self.person.pk})
        )

    def test_valid_form_displays_success_message(self):
        """Test that successful form submission displays success message."""
        self.client.login(username="officer_edit", password="testpass")
        url = reverse("person_edit", kwargs={"pk": self.person.pk})

        response = self.client.post(url, {
            "name": "New Name",
            "is_worker": False,
            "is_vendor": False,
            "is_client": False,
            "is_shareholder": False,
            "is_internal": False,
            "active": True,
        }, follow=True)

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("updated successfully", str(messages[0]))

    def test_invalid_form_missing_name(self):
        """Test that form submission without name shows validation error."""
        self.client.login(username="officer_edit", password="testpass")
        url = reverse("person_edit", kwargs={"pk": self.person.pk})

        response = self.client.post(url, {
            "name": "",
            "is_worker": False,
            "is_vendor": False,
            "is_client": False,
            "is_shareholder": False,
            "is_internal": False,
            "active": True,
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)

    def test_invalid_form_duplicate_name(self):
        """Test that form submission with duplicate name shows validation error."""
        # Create another person with different name
        other_person = Entity.create(EntityType.PERSON, name="Existing Person")

        self.client.login(username="officer_edit", password="testpass")
        url = reverse("person_edit", kwargs={"pk": self.person.pk})

        response = self.client.post(url, {
            "name": "Existing Person",
            "is_worker": False,
            "is_vendor": False,
            "is_client": False,
            "is_shareholder": False,
            "is_internal": False,
            "active": True,
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)
        self.assertIn("already exists", str(response.context["form"].errors["name"]))

    def test_person_can_use_own_name(self):
        """Test that person can keep their own name when editing."""
        self.client.login(username="officer_edit", password="testpass")
        url = reverse("person_edit", kwargs={"pk": self.person.pk})

        response = self.client.post(url, {
            "name": "John Doe",  # Same name as current
            "is_worker": True,
            "is_vendor": False,
            "is_client": False,
            "is_shareholder": False,
            "is_internal": False,
            "active": True,
        })

        self.assertEqual(response.status_code, 302)
        self.person.refresh_from_db()
        self.assertEqual(self.person.name, "John Doe")

    def test_edit_non_person_entity_shows_error(self):
        """Test that editing a non-person entity shows error and redirects."""
        project = Entity.create(EntityType.PROJECT, name="Test Project")
        self.client.login(username="officer_edit", password="testpass")
        url = reverse("person_edit", kwargs={"pk": project.pk})

        response = self.client.post(url, {
            "name": "New Name",
            "is_worker": False,
            "is_vendor": False,
            "is_client": False,
            "is_shareholder": False,
            "is_internal": False,
            "active": True,
        }, follow=True)

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("not a Person" in str(m) for m in messages))

    def test_unauthenticated_user_redirected(self):
        """Test that unauthenticated users are redirected."""
        url = reverse("person_edit", kwargs={"pk": self.person.pk})
        response = self.client.post(url, {
            "name": "New Name",
            "is_worker": False,
            "is_vendor": False,
            "is_client": False,
            "is_shareholder": False,
            "is_internal": False,
            "active": True,
        })
        self.assertEqual(response.status_code, 302)

    def test_nonexistent_entity_returns_404(self):
        """Test that POST to non-existent entity returns 404."""
        self.client.login(username="officer_edit", password="testpass")
        url = reverse("person_edit", kwargs={"pk": 99999})

        response = self.client.post(url, {
            "name": "New Name",
            "is_worker": False,
            "is_vendor": False,
            "is_client": False,
            "is_shareholder": False,
            "is_internal": False,
            "active": True,
        })

        self.assertEqual(response.status_code, 404)
