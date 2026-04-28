

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



class SaleWizardInvoiceViewTest(TestCase):
    """Test sale invoice view."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer(username="sale_invoice")
        self.project = _make_project()
        self.client_entity = _make_client()
        _link_client_to_project(self.project, self.client_entity)

        # Set up complete session
        session = self.client.session
        session[f"sale_wizard_{self.project.pk}"] = {
            "date": date.today().isoformat(),
            "client_id": self.client_entity.pk,
            "description": "Test sale",
            "total_amount": "1000.00",
            "items": [],
        }
        session.save()

    def test_invoice_view_requires_session(self):
        """Test invoice view requires complete session data."""
        self.client.login(username="sale_invoice", password="testpass")
        response = self.client.get(
            reverse("sale_invoice", kwargs={"pk": self.project.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("project", response.context)

    def test_invoice_view_no_session_redirects(self):
        """Test invoice view redirects without session."""
        project_new = _make_project(name="New Project for Invoice")
        client_entity = _make_client(name="Test Client Invoice")
        _link_client_to_project(project_new, client_entity)

        self.client.login(username="sale_invoice", password="testpass")
        response = self.client.get(
            reverse("sale_invoice", kwargs={"pk": project_new.pk})
        )

        self.assertEqual(response.status_code, 302)
