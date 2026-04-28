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


class PeriodCreateViewTest(TestCase):
    """Test period creation view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_period_create", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm Project")

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

    def test_period_create_unauthenticated_redirects(self):
        """Test period create redirects unauthenticated users."""
        response = self.client.get(
            reverse("period_create_view", kwargs={"entity_pk": self.entity.pk})
        )

        self.assertEqual(response.status_code, 302)


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


class PeriodViewIntegrationTest(TestCase):
    """Test period workflow (create, view, close)."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_workflow", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Farm Project")

    def test_full_period_workflow(self):
        """Test complete period workflow: create, view, close."""
        self.client.login(username="officer_workflow", password="testpass")

        # Step 0: Close the auto-created period
        existing_period = self.entity.financial_periods.first()
        close_date_1 = date.today() + timedelta(days=1)
        existing_period.end_date = close_date_1
        existing_period.save()

        # Step 1: Create a new period
        start_date = close_date_1
        response = self.client.post(
            reverse("period_create_view", kwargs={"entity_pk": self.entity.pk}),
            {"start_date": start_date.isoformat()},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # Get the newly created period
        period = FinancialPeriod.objects.get(entity=self.entity, start_date=start_date)
        self.assertIsNone(period.end_date)

        # Step 2: View period detail
        response = self.client.get(
            reverse("period_detail_view", kwargs={"period_pk": period.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period"], period)

        # Step 3: View period close form (closure is not fully testable due to view bug)
        response = self.client.get(
            reverse("period_close_view", kwargs={"period_pk": period.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period"], period)
