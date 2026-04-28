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


class OperationDetailViewTest(TestCase):
    """Test GET request to operation detail view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_op_detail", is_staff=True)
        from apps.app_operation.models.operation_type import OperationType
        from apps.app_operation.models.proxies import CashInjectionOperation
        from decimal import Decimal
        import datetime

        world = Entity.create(EntityType.WORLD)
        self.destination = Entity.create(EntityType.PERSON, name="Destination")
        self.operation = CashInjectionOperation.objects.create(
            source=world,
            destination=self.destination,
            officer=self.officer,
            operation_type=OperationType.CASH_INJECTION,
            amount=Decimal("100.00"),
            date=datetime.date.today(),
            deletable=False,
        )

    def test_authorized_user_can_load_operation_detail(self):
        """Test that logged-in user can view operation detail."""
        self.client.login(username="officer_op_detail", password="testpass")
        url = reverse("operation_detail_view", kwargs={"pk": self.operation.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("operation", response.context)
        self.assertEqual(response.context["operation"], self.operation)

    def test_operation_detail_displays_transactions(self):
        """Test that operation detail displays associated transactions."""
        self.client.login(username="officer_op_detail", password="testpass")
        url = reverse("operation_detail_view", kwargs={"pk": self.operation.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("operation", response.context)

    def test_nonexistent_operation_returns_404(self):
        """Test that requesting non-existent operation returns 404."""
        self.client.login(username="officer_op_detail", password="testpass")
        url = reverse("operation_detail_view", kwargs={"pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
