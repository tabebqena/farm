

"""Comprehensive tests for period views (list, detail, create, close)."""

from datetime import date, timedelta

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.tests.general import make_user
from apps.app_operation.models.period import FinancialPeriod



class PeriodCloseViewTest(TestCase):
    """Test period closing view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_period_close", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm Project")
        self.period = self.entity.financial_periods.first()

    def test_period_close_get_renders_form(self):
        """Test GET request to period_close shows form."""
        self.client.login(username="officer_period_close", password="testpass")
        response = self.client.get(
            reverse("period_close_view", kwargs={"period_pk": self.period.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period"], self.period)

    def test_period_close_form_loads(self):
        """Test period close form can be loaded for an open period."""
        self.client.login(username="officer_period_close", password="testpass")
        self.assertIsNone(self.period.end_date)

        response = self.client.get(
            reverse("period_close_view", kwargs={"period_pk": self.period.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period"], self.period)

    def test_period_close_form_for_open_period(self):
        """Test period close form is available for open periods."""
        self.client.login(username="officer_period_close", password="testpass")

        response = self.client.get(
            reverse("period_close_view", kwargs={"period_pk": self.period.pk})
        )

        self.assertEqual(response.status_code, 200)
        # Form should be shown for open period
        self.assertIn("period", response.context)

    def test_period_close_shows_period_info(self):
        """Test period close view shows correct period information."""
        self.client.login(username="officer_period_close", password="testpass")
        response = self.client.get(
            reverse("period_close_view", kwargs={"period_pk": self.period.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period"], self.period)

    def test_period_close_already_closed_returns_error(self):
        """Test trying to close an already-closed period returns error."""
        self.period.end_date = date.today() + timedelta(days=1)
        self.period.save()

        self.client.login(username="officer_period_close", password="testpass")
        response = self.client.get(
            reverse("period_close_view", kwargs={"period_pk": self.period.pk})
        )

        # Should return error response
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.context)

    def test_period_close_nonexistent_returns_404(self):
        """Test closing non-existent period returns 404."""
        self.client.login(username="officer_period_close", password="testpass")
        response = self.client.get(
            reverse("period_close_view", kwargs={"period_pk": 99999})
        )

        self.assertEqual(response.status_code, 404)

    def test_period_close_unauthenticated_redirects(self):
        """Test period close redirects unauthenticated users."""
        response = self.client.get(
            reverse("period_close_view", kwargs={"period_pk": self.period.pk})
        )

        self.assertEqual(response.status_code, 302)
