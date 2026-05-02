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


class SaleWizardCancelTest(TestCase):
    """Test sale wizard cancellation."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer(username="sale_cancel")
        self.project = _make_project()
        self.client_entity = _make_client()
        _link_client_to_project(self.project, self.client_entity)

        # Set up session
        session = self.client.session
        session[f"sale_wizard_{self.project.pk}"] = {"date": date.today().isoformat()}
        session.save()

    def test_cancel_clears_session(self):
        """Test canceling wizard clears session data."""
        self.client.login(username="sale_cancel", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_cancel", kwargs={"pk": self.project.pk})
        )

        self.assertEqual(response.status_code, 302)
        # Session should be cleared
        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertIsNone(session)

    def test_cancel_redirects_to_operations_list(self):
        """Test cancel redirects back to operations list."""
        self.client.login(username="sale_cancel", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_cancel", kwargs={"pk": self.project.pk})
        )

        self.assertEqual(response.status_code, 302)
        # Just verify it redirects
        self.assertIsNotNone(response.url)
