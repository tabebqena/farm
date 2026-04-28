

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



class PeriodListViewTest(TestCase):
    """Test GET request to period list view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_period", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm Project")

    def test_authorized_user_can_load_period_list(self):
        """Test that logged-in user can view period list."""
        self.client.login(username="officer_period", password="testpass")
        url = reverse("period_list_view", kwargs={"entity_pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("periods", response.context)

    def test_period_list_displays_all_periods(self):
        """Test that period list displays entity's periods."""
        self.client.login(username="officer_period", password="testpass")
        url = reverse("period_list_view", kwargs={"entity_pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        periods = response.context["periods"]
        # Entity auto-creates one period
        self.assertGreaterEqual(len(periods), 1)
