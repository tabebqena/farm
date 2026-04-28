

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



class SaleWizardIntegrationTest(TestCase):
    """Test complete sale wizard workflow."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer(username="sale_integration")
        self.project = _make_project()
        self.client_entity = _make_client()
        _link_client_to_project(self.project, self.client_entity)

    def test_complete_sale_wizard_flow(self):
        """Test completing all wizard steps."""
        self.client.login(username="sale_integration", password="testpass")

        # Step 1: Basic info
        response = self.client.post(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk}),
            {
                "date": date.today().isoformat(),
                "client": self.client_entity.pk,
                "description": "Complete sale test",
            },
        )
        self.assertEqual(response.status_code, 302)

        # Step 2: Total amount
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 2}),
            {"total_amount": "2500.00"},
        )
        self.assertEqual(response.status_code, 302)

        # Step 3: Payment
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3}),
            {"amount_paid": "1000.00"},
        )
        self.assertEqual(response.status_code, 302)

        # Verify session is complete
        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertEqual(session["total_amount"], "2500.00")
        self.assertEqual(session["amount_paid"], "1000.00")

    def test_wizard_session_persistence(self):
        """Test wizard session persists across steps."""
        self.client.login(username="sale_integration", password="testpass")

        # Step 1
        self.client.post(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk}),
            {
                "date": date.today().isoformat(),
                "client": self.client_entity.pk,
                "description": "Persistence test",
            },
        )

        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertEqual(session["description"], "Persistence test")

        # Step 2
        self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 2}),
            {"total_amount": "1500.00"},
        )

        # Verify step 1 data still in session
        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertEqual(session["description"], "Persistence test")
        self.assertEqual(session["total_amount"], "1500.00")
