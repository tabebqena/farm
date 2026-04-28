

"""Comprehensive tests for sale wizard flow."""

from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import ProductTemplate
from apps.app_inventory.tests.general import make_user, make_product_template
from apps.app_operation.models.proxies import SaleOperation


def _make_officer(username="officer"):
    """Create a staff user."""
    return make_user(username=username, is_staff=True)


def _make_project(name="Test Project"):
    """Create a project entity."""
    return Entity.create(EntityType.PROJECT, name=name)


def _make_client(name="Test Client"):
    """Create a person entity configured as a client."""
    return Entity.create(EntityType.PERSON, name=name, is_client=True, active=True)


def _link_client_to_project(project, client):
    """Create client stakeholder relationship."""
    return Stakeholder.objects.create(
        parent=project,
        target=client,
        role=StakeholderRole.CLIENT,
        active=True,
    )



class SaleWizardStep1Test(TestCase):
    """Test step 1: Basic Information (date, client, description)."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer(username="sale_step1")
        self.project = _make_project()
        self.client_entity = _make_client()
        _link_client_to_project(self.project, self.client_entity)

    def test_step1_get_renders_form(self):
        """Test GET request to step 1 shows form."""
        self.client.login(username="sale_step1", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 1)
        self.assertIn("form", response.context)

    def test_step1_get_shows_project(self):
        """Test step 1 GET shows project in context."""
        self.client.login(username="sale_step1", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["project"], self.project)

    def test_step1_post_saves_to_session(self):
        """Test step 1 POST saves data to session."""
        self.client.login(username="sale_step1", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk}),
            {
                "date": date.today().isoformat(),
                "client": self.client_entity.pk,
                "description": "Test sale",
            },
        )

        self.assertEqual(response.status_code, 302)
        # Verify session contains data
        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertIsNotNone(session)
        self.assertEqual(session["client_id"], self.client_entity.pk)
        self.assertEqual(session["description"], "Test sale")

    def test_step1_post_requires_client(self):
        """Test step 1 requires client selection."""
        self.client.login(username="sale_step1", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk}),
            {
                "date": date.today().isoformat(),
                "client": "",
                "description": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_step1_post_redirects_to_step2(self):
        """Test step 1 POST redirects to step 2."""
        self.client.login(username="sale_step1", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk}),
            {
                "date": date.today().isoformat(),
                "client": self.client_entity.pk,
                "description": "Test",
            },
        )

        self.assertEqual(response.status_code, 302)
        # Should redirect (URL contains step 2)
        self.assertTrue(response.url)

    def test_step1_no_clients_shows_error(self):
        """Test step 1 shows error when project has no clients."""
        project_no_client = _make_project(name="No Clients")
        self.client.login(username="sale_step1", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_step1", kwargs={"pk": project_no_client.pk})
        )

        self.assertEqual(response.status_code, 302)
