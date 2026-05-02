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


class SaleWizardStep3Test(TestCase):
    """Test step 3: Payment (optional)."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer(username="sale_step3")
        self.project = _make_project()
        self.client_entity = _make_client()
        _link_client_to_project(self.project, self.client_entity)

        # Set up session with step 1 and 2 data
        session = self.client.session
        session[f"sale_wizard_{self.project.pk}"] = {
            "date": date.today().isoformat(),
            "client_id": self.client_entity.pk,
            "description": "Test sale",
            "total_amount": "1000.00",
        }
        session.save()

    def test_step3_get_renders_form(self):
        """Test GET request to step 3 shows form."""
        self.client.login(username="sale_step3", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 3)

    def test_step3_post_payment_less_than_total(self):
        """Test step 3 accepts partial payment."""
        self.client.login(username="sale_step3", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3}),
            {"amount_paid": "500.00"},
        )

        self.assertEqual(response.status_code, 302)
        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertEqual(session["amount_paid"], "500.00")

    def test_step3_post_payment_equal_to_total(self):
        """Test step 3 accepts full payment."""
        self.client.login(username="sale_step3", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3}),
            {"amount_paid": "1000.00"},
        )

        self.assertEqual(response.status_code, 302)

    def test_step3_post_payment_exceeds_total_rejected(self):
        """Test step 3 rejects payment exceeding total."""
        self.client.login(username="sale_step3", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3}),
            {"amount_paid": "1500.00"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        # Form should have error

    def test_step3_post_no_payment_allowed(self):
        """Test step 3 allows skipping payment."""
        self.client.login(username="sale_step3", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3}),
            {"amount_paid": "0"},
        )

        self.assertEqual(response.status_code, 302)

    def test_step3_redirects_to_invoice(self):
        """Test step 3 POST redirects to invoice view."""
        self.client.login(username="sale_step3", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3}),
            {"amount_paid": "500.00"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("invoice", response.url)
