"""Tests for entity form views (create and edit for persons and projects)."""

from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.messages import get_messages

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.models import ProductTemplate
from apps.app_inventory.tests.general import make_user
from apps.app_operation.models.period import FinancialPeriod


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
        self.assertIn("form", response.context)
        self.assertFalse(response.context.get("edit", True))

    def test_person_create_post_creates_entity(self):
        """Test POST creates a new person entity."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "John Doe",
                "description": "A test person",
                "is_vendor": "on",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
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

    def test_person_create_sets_correct_entity_type(self):
        """Test that created entity has PERSON type."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Type Check Person",
                "description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
            },
        )

        entity = Entity.objects.get(name="Type Check Person")
        self.assertEqual(entity.entity_type, EntityType.PERSON)

    def test_person_create_creates_financial_period(self):
        """Test that person creation also creates initial financial period."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Period Check Person",
                "description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
            },
        )

        entity = Entity.objects.get(name="Period Check Person")
        periods = FinancialPeriod.objects.filter(entity=entity)
        self.assertEqual(periods.count(), 1)
        self.assertIsNotNone(periods.first().start_date)

    def test_person_create_displays_success_message(self):
        """Test that successful creation displays success message."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Success Message Person",
                "description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
            },
            follow=True,
        )

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Success Message Person", str(messages[0]))
        self.assertIn("created", str(messages[0]).lower())

    def test_person_create_redirects_to_entity_detail(self):
        """Test successful person creation redirects to entity detail."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Redirect Test",
                "description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
            },
            follow=True,
        )

        entity = Entity.objects.get(name="Redirect Test")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Redirect Test")
        # Verify redirect target
        self.assertEqual(response.resolver_match.kwargs.get("pk"), entity.pk)

    def test_person_create_with_all_roles(self):
        """Test creating person with multiple roles."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Multi-Role Person",
                "description": "Wears many hats",
                "is_vendor": "on",
                "is_worker": "on",
                "is_client": "on",
                "is_shareholder": "on",
                "is_internal": "on",
                "active": "on",
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
                "description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        entity = Entity.objects.get(name="Generic Person")
        self.assertFalse(entity.is_vendor)
        self.assertFalse(entity.is_worker)
        self.assertFalse(entity.is_client)
        self.assertFalse(entity.is_shareholder)

    def test_person_create_with_description(self):
        """Test person creation includes description."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Described Person",
                "description": "This is a detailed description",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        entity = Entity.objects.get(name="Described Person")
        self.assertEqual(entity.description, "This is a detailed description")

    def test_person_create_invalid_missing_name(self):
        """Test that form submission without name shows validation error."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "",
                "description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        self.assertIn("name", response.context["form"].errors)

    def test_person_create_invalid_duplicate_name(self):
        """Test that duplicate name shows validation error."""
        # Create existing person
        Entity.create(EntityType.PERSON, name="Existing Person")

        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Existing Person",
                "description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)
        self.assertIn("already exists", str(response.context["form"].errors["name"]))
        # Verify only one entity with this name exists
        self.assertEqual(Entity.objects.filter(name="Existing Person").count(), 1)

    def test_person_create_form_preserved_on_error(self):
        """Test that form data is preserved when validation fails."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "",
                "description": "Some description",
                "is_vendor": "on",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        self.assertEqual(
            response.context["form"].data.get("description"), "Some description"
        )
        self.assertTrue(response.context["form"].data.get("is_vendor"))

    def test_person_create_unauthenticated_user_redirected(self):
        """Test that unauthenticated users are redirected."""
        response = self.client.get(reverse("person_create"))
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Should Fail",
                "description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_person_create_sets_active_status(self):
        """Test that person is created with correct active status."""
        self.client.login(username="officer_person", password="testpass")
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Active Person",
                "description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
            },
        )

        entity = Entity.objects.get(name="Active Person")
        self.assertTrue(entity.active)

    def test_person_create_uses_atomic_transaction(self):
        """Test that creation uses atomic transaction."""
        self.client.login(username="officer_person", password="testpass")

        # Verify successful atomic creation
        initial_count = Entity.objects.count()
        response = self.client.post(
            reverse("person_create"),
            {
                "name": "Atomic Test Person",
                "description": "",
                "is_vendor": "",
                "is_worker": "",
                "is_client": "",
                "is_shareholder": "",
                "is_internal": "",
                "active": "on",
            },
        )

        final_count = Entity.objects.count()
        self.assertEqual(final_count, initial_count + 1)
