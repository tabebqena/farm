"""Comprehensive tests for period views (list, detail, create, close)."""

from datetime import date, timedelta

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType
from apps.app_inventory.tests.general import make_user
from apps.app_operation.models.period import FinancialPeriod


class PeriodCreateViewTest(TestCase):
    """Test period creation view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_period_create", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm Project")

    def _create_inactive_entity(self):
        """Helper to create an inactive entity for tests that need to bypass the guard."""
        inactive_entity = Entity.create(EntityType.PROJECT, name="Inactive Project")
        inactive_entity.active = False
        inactive_entity.save()
        return inactive_entity

    def test_period_create_get_renders_form(self):
        """Test GET request to period_create shows form."""
        self.client.login(username="officer_period_create", password="testpass")
        response = self.client.get(
            reverse("period_create_view", kwargs={"entity_pk": self.entity.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["entity"], self.entity)

    def test_period_create_post_creates_period(self):
        """Test POST to period_create creates a new financial period after closing existing."""
        self.client.login(username="officer_period_create", password="testpass")

        # Close the auto-created period first
        existing_period = self.entity.financial_periods.first()
        close_date = date.today() + timedelta(days=1)
        existing_period.end_date = close_date
        existing_period.save()

        # Now create a new period
        start_date = close_date + timedelta(days=1)
        response = self.client.post(
            reverse("period_create_view", kwargs={"entity_pk": self.entity.pk}),
            {"start_date": start_date.isoformat()},
        )

        self.assertEqual(response.status_code, 302)
        # Verify period was created
        period = FinancialPeriod.objects.filter(entity=self.entity, start_date=start_date)
        self.assertTrue(period.exists())

    def test_period_create_redirects_to_list(self):
        """Test successful period creation redirects to period list."""
        self.client.login(username="officer_period_create", password="testpass")

        # Close the auto-created period first
        existing_period = self.entity.financial_periods.first()
        close_date = date.today() + timedelta(days=1)
        existing_period.end_date = close_date
        existing_period.save()

        start_date = close_date + timedelta(days=1)
        response = self.client.post(
            reverse("period_create_view", kwargs={"entity_pk": self.entity.pk}),
            {"start_date": start_date.isoformat()},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        # Should redirect to period list
        self.assertContains(response, self.entity.name)

    def test_period_create_requires_start_date(self):
        """Test period creation requires a start date."""
        self.client.login(username="officer_period_create", password="testpass")
        response = self.client.post(
            reverse("period_create_view", kwargs={"entity_pk": self.entity.pk}),
            {"start_date": ""},
        )

        # Should return error response
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.context)

    def test_period_create_nonexistent_entity_returns_404(self):
        """Test creating period for non-existent entity returns 404."""
        self.client.login(username="officer_period_create", password="testpass")
        response = self.client.get(
            reverse("period_create_view", kwargs={"entity_pk": 99999})
        )

        self.assertEqual(response.status_code, 404)

    def test_period_create_blocks_active_entity_with_existing_periods(self):
        """Test period creation is blocked for active entities with existing periods."""
        self.client.login(username="officer_period_create", password="testpass")
        # self.entity is active and has auto-created period
        response = self.client.post(
            reverse("period_create_view", kwargs={"entity_pk": self.entity.pk}),
            {"start_date": date.today().isoformat()},
        )

        # Should redirect to period list
        self.assertEqual(response.status_code, 302)

    def test_period_create_unauthenticated_redirects(self):
        """Test period create redirects unauthenticated users."""
        response = self.client.get(
            reverse("period_create_view", kwargs={"entity_pk": self.entity.pk})
        )

        self.assertEqual(response.status_code, 302)
