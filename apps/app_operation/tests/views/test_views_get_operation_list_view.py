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


class OperationListViewTest(TestCase):
    """Test GET request to operation list view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_ops", is_staff=True)
        self.person = Entity.create(EntityType.PERSON, name="Test Person")

    def test_authorized_user_can_load_operation_list(self):
        """Test that logged-in user can view operation list."""
        self.client.login(username="officer_ops", password="testpass")
        url = reverse("operation_list_view", kwargs={"person_pk": self.person.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("operations", response.context)

    def test_operation_list_with_multiple_operations(self):
        """Test that operation list displays all operations."""
        from apps.app_operation.models.operation_type import OperationType
        from apps.app_operation.models.proxies import CashInjectionOperation
        from decimal import Decimal

        # Create some cash injection operations
        world = Entity.create(EntityType.WORLD)
        for _ in range(3):
            CashInjectionOperation.objects.create(
                source=world,
                destination=self.person,
                officer=self.officer,
                operation_type=OperationType.CASH_INJECTION,
                amount=Decimal("100.00"),
                date=__import__("datetime").date.today(),
                deletable=False,
            )

        self.client.login(username="officer_ops", password="testpass")
        url = reverse("operation_list_view", kwargs={"person_pk": self.person.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        operations = response.context["operations"]
        self.assertGreater(len(operations), 0)

    def test_nonexistent_person_returns_404(self):
        """Test that requesting non-existent person returns 404."""
        self.client.login(username="officer_ops", password="testpass")
        url = reverse("operation_list_view", kwargs={"person_pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
