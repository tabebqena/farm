

"""Comprehensive tests for period views (list, detail, create, close)."""

from datetime import date, timedelta

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.tests.general import make_user
from apps.app_operation.models.period import FinancialPeriod



class PeriodListViewEnhancedTest(TestCase):
    """Enhanced tests for period list view including multiple periods."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_period_list", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm Project")

    def test_period_list_shows_periods_in_descending_order(self):
        """Test period list shows periods ordered by start_date descending."""
        self.client.login(username="officer_period_list", password="testpass")

        # Get auto-created period and close it
        first_period = self.entity.financial_periods.first()
        close_date = date.today() + timedelta(days=1)
        first_period.end_date = close_date
        first_period.save()

        # Create a second period
        second_period = FinancialPeriod.objects.create(
            entity=self.entity, start_date=close_date
        )

        response = self.client.get(
            reverse("period_list_view", kwargs={"entity_pk": self.entity.pk})
        )

        self.assertEqual(response.status_code, 200)
        periods = list(response.context["periods"])
        self.assertGreaterEqual(len(periods), 2)
        # Should be in descending order (newer first)
        self.assertEqual(periods[0].pk, second_period.pk)

    def test_period_list_includes_entity_in_context(self):
        """Test period list includes the entity in context."""
        self.client.login(username="officer_period_list", password="testpass")
        response = self.client.get(
            reverse("period_list_view", kwargs={"entity_pk": self.entity.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["entity"], self.entity)

    def test_period_list_nonexistent_entity_returns_404(self):
        """Test period list with non-existent entity returns 404."""
        self.client.login(username="officer_period_list", password="testpass")
        response = self.client.get(
            reverse("period_list_view", kwargs={"entity_pk": 99999})
        )

        self.assertEqual(response.status_code, 404)

    def test_period_list_unauthenticated_redirects(self):
        """Test period list redirects unauthenticated users."""
        response = self.client.get(
            reverse("period_list_view", kwargs={"entity_pk": self.entity.pk})
        )

        self.assertEqual(response.status_code, 302)
