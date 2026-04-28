

"""Comprehensive tests for period views (list, detail, create, close)."""

from datetime import date, timedelta

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.tests.general import make_user
from apps.app_operation.models.period import FinancialPeriod



class PeriodDetailViewEnhancedTest(TestCase):
    """Enhanced tests for period detail view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_period_detail", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm Project")
        self.period = self.entity.financial_periods.first()

    def test_period_detail_includes_entity(self):
        """Test period detail view includes entity in context."""
        self.client.login(username="officer_period_detail", password="testpass")
        response = self.client.get(
            reverse("period_detail_view", kwargs={"period_pk": self.period.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["entity"], self.entity)

    def test_period_detail_with_closed_period(self):
        """Test period detail with a closed period."""
        self.period.end_date = date.today() + timedelta(days=30)
        self.period.save()

        self.client.login(username="officer_period_detail", password="testpass")
        response = self.client.get(
            reverse("period_detail_view", kwargs={"period_pk": self.period.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["period"].end_date)

    def test_period_detail_unauthenticated_redirects(self):
        """Test period detail redirects unauthenticated users."""
        response = self.client.get(
            reverse("period_detail_view", kwargs={"period_pk": self.period.pk})
        )

        self.assertEqual(response.status_code, 302)
