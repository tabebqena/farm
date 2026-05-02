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


class PeriodDetailViewTest(TestCase):
    """Test GET request to period detail view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_period_detail", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm Project")
        # Get the auto-created period
        self.period = self.entity.financial_periods.first()

    def test_authorized_user_can_load_period_detail(self):
        """Test that logged-in user can view period detail."""
        self.client.login(username="officer_period_detail", password="testpass")
        url = reverse("period_detail_view", kwargs={"period_pk": self.period.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("period", response.context)
        self.assertEqual(response.context["period"], self.period)

    def test_period_detail_shows_operations(self):
        """Test that period detail shows associated operations."""
        self.client.login(username="officer_period_detail", password="testpass")
        url = reverse("period_detail_view", kwargs={"period_pk": self.period.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("period", response.context)

    def test_nonexistent_period_returns_404(self):
        """Test that requesting non-existent period returns 404."""
        self.client.login(username="officer_period_detail", password="testpass")
        url = reverse("period_detail_view", kwargs={"period_pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
