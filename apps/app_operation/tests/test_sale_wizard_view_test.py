

"""GET request tests for app_operation views.

Tests that ensure authorized users can make GET requests to pages without errors.
"""

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.tests.general import (
    make_operation,
    make_product_template,
    make_user,
)
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import PurchaseOperation, SaleOperation



class SaleWizardViewTest(TestCase):
    """Test GET request to sale wizard views."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_sale", is_staff=True)
        self.project = Entity.create(EntityType.PROJECT, name="Farm")
        self.client_entity = Entity.create(EntityType.PERSON, name="Client")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.client_entity,
            active=True,
            role=StakeholderRole.CLIENT,
        )

    def test_authorized_user_can_load_sale_wizard_step1(self):
        """Test that logged-in user can view sale wizard step 1."""
        self.client.login(username="officer_sale", password="testpass")
        url = reverse("sale_wizard_step1", kwargs={"pk": self.project.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_sale_wizard_with_clients(self):
        """Test sale wizard loads with available clients."""
        self.client.login(username="officer_sale", password="testpass")
        url = reverse("sale_wizard_step1", kwargs={"pk": self.project.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
