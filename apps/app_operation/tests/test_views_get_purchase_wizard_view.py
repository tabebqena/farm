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


class PurchaseWizardViewTest(TestCase):
    """Test GET request to purchase wizard views."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_purchase", is_staff=True)
        self.project = Entity.create(EntityType.PROJECT, name="Farm")
        self.vendor = Entity.create(EntityType.PERSON, name="Vendor")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )

    def test_authorized_user_can_load_purchase_wizard_step1(self):
        """Test that logged-in user can view purchase wizard step 1."""
        self.client.login(username="officer_purchase", password="testpass")
        url = reverse("purchase_wizard_step1", kwargs={"pk": self.project.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_purchase_wizard_with_vendors(self):
        """Test purchase wizard loads with available vendors."""
        self.client.login(username="officer_purchase", password="testpass")
        url = reverse("purchase_wizard_step1", kwargs={"pk": self.project.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
