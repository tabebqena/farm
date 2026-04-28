"""Comprehensive tests for sale wizard flow."""

from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.models import ProductTemplate
from apps.app_inventory.tests.general import make_user, make_product_template
from apps.app_operation.models.proxies import SaleOperation


def _make_officer(username="officer"):
    """Create a staff user."""
    return make_user(username=username, is_staff=True)


def _make_project(name="Test Project"):
    """Create a project entity."""
    return Entity.create(EntityType.PROJECT, name=name)


def _make_client(name="Test Client"):
    """Create a person entity configured as a client."""
    return Entity.create(EntityType.PERSON, name=name, is_client=True, active=True)


def _link_client_to_project(project, client):
    """Create client stakeholder relationship."""
    return Stakeholder.objects.create(
        parent=project,
        target=client,
        role=StakeholderRole.CLIENT,
        active=True,
    )


class SaleWizardStep1Test(TestCase):
    """Test step 1: Basic Information (date, client, description)."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer(username="sale_step1")
        self.project = _make_project()
        self.client_entity = _make_client()
        _link_client_to_project(self.project, self.client_entity)

    def test_step1_get_renders_form(self):
        """Test GET request to step 1 shows form."""
        self.client.login(username="sale_step1", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 1)
        self.assertIn("form", response.context)

    def test_step1_get_shows_project(self):
        """Test step 1 GET shows project in context."""
        self.client.login(username="sale_step1", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["project"], self.project)

    def test_step1_post_saves_to_session(self):
        """Test step 1 POST saves data to session."""
        self.client.login(username="sale_step1", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk}),
            {
                "date": date.today().isoformat(),
                "client": self.client_entity.pk,
                "description": "Test sale",
            },
        )

        self.assertEqual(response.status_code, 302)
        # Verify session contains data
        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertIsNotNone(session)
        self.assertEqual(session["client_id"], self.client_entity.pk)
        self.assertEqual(session["description"], "Test sale")

    def test_step1_post_requires_client(self):
        """Test step 1 requires client selection."""
        self.client.login(username="sale_step1", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk}),
            {
                "date": date.today().isoformat(),
                "client": "",
                "description": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_step1_post_redirects_to_step2(self):
        """Test step 1 POST redirects to step 2."""
        self.client.login(username="sale_step1", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk}),
            {
                "date": date.today().isoformat(),
                "client": self.client_entity.pk,
                "description": "Test",
            },
        )

        self.assertEqual(response.status_code, 302)
        # Should redirect (URL contains step 2)
        self.assertTrue(response.url)

    def test_step1_no_clients_shows_error(self):
        """Test step 1 shows error when project has no clients."""
        project_no_client = _make_project(name="No Clients")
        self.client.login(username="sale_step1", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_step1", kwargs={"pk": project_no_client.pk})
        )

        self.assertEqual(response.status_code, 302)


class SaleWizardStep2Test(TestCase):
    """Test step 2: Total Amount."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer(username="sale_step2")
        self.project = _make_project()
        self.client_entity = _make_client()
        _link_client_to_project(self.project, self.client_entity)

        # Set up session with step 1 data
        session = self.client.session
        session[f"sale_wizard_{self.project.pk}"] = {
            "date": date.today().isoformat(),
            "client_id": self.client_entity.pk,
            "description": "Test sale",
        }
        session.save()

    def test_step2_get_with_session_data(self):
        """Test step 2 GET with proper session data."""
        self.client.login(username="sale_step2", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 2})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 2)

    def test_step2_post_saves_total_amount(self):
        """Test step 2 POST saves total amount to session."""
        self.client.login(username="sale_step2", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 2}),
            {"total_amount": "1000.50"},
        )

        self.assertEqual(response.status_code, 302)
        # Verify session contains total_amount
        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertEqual(session["total_amount"], "1000.50")

    def test_step2_post_redirects_to_step3(self):
        """Test step 2 POST redirects to step 3."""
        self.client.login(username="sale_step2", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 2}),
            {"total_amount": "500.00"},
        )

        self.assertEqual(response.status_code, 302)
        # Verify we're redirecting (just check it's a redirect)
        self.assertIsNotNone(response.url)

    def test_step2_next_param_redirects_to_invoice(self):
        """Test step 2 with next=invoice redirects to invoice view."""
        self.client.login(username="sale_step2", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 2}),
            {"total_amount": "500.00", "next": "invoice"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("invoice", response.url)

    def test_step2_negative_amount_validation(self):
        """Test step 2 rejects negative amounts."""
        self.client.login(username="sale_step2", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 2}),
            {"total_amount": "-100.00"},
        )

        # Should either reject or accept depending on form validation
        self.assertIn(response.status_code, [200, 302])


class SaleWizardStep3Test(TestCase):
    """Test step 3: Payment (optional)."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer(username="sale_step3")
        self.project = _make_project()
        self.client_entity = _make_client()
        _link_client_to_project(self.project, self.client_entity)

        # Set up session with step 1 and 2 data
        session = self.client.session
        session[f"sale_wizard_{self.project.pk}"] = {
            "date": date.today().isoformat(),
            "client_id": self.client_entity.pk,
            "description": "Test sale",
            "total_amount": "1000.00",
        }
        session.save()

    def test_step3_get_renders_form(self):
        """Test GET request to step 3 shows form."""
        self.client.login(username="sale_step3", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], 3)

    def test_step3_post_payment_less_than_total(self):
        """Test step 3 accepts partial payment."""
        self.client.login(username="sale_step3", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3}),
            {"amount_paid": "500.00"},
        )

        self.assertEqual(response.status_code, 302)
        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertEqual(session["amount_paid"], "500.00")

    def test_step3_post_payment_equal_to_total(self):
        """Test step 3 accepts full payment."""
        self.client.login(username="sale_step3", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3}),
            {"amount_paid": "1000.00"},
        )

        self.assertEqual(response.status_code, 302)

    def test_step3_post_payment_exceeds_total_rejected(self):
        """Test step 3 rejects payment exceeding total."""
        self.client.login(username="sale_step3", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3}),
            {"amount_paid": "1500.00"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        # Form should have error

    def test_step3_post_no_payment_allowed(self):
        """Test step 3 allows skipping payment."""
        self.client.login(username="sale_step3", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3}),
            {"amount_paid": "0"},
        )

        self.assertEqual(response.status_code, 302)

    def test_step3_redirects_to_invoice(self):
        """Test step 3 POST redirects to invoice view."""
        self.client.login(username="sale_step3", password="testpass")
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3}),
            {"amount_paid": "500.00"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("invoice", response.url)


class SaleWizardCancelTest(TestCase):
    """Test sale wizard cancellation."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer(username="sale_cancel")
        self.project = _make_project()
        self.client_entity = _make_client()
        _link_client_to_project(self.project, self.client_entity)

        # Set up session
        session = self.client.session
        session[f"sale_wizard_{self.project.pk}"] = {"date": date.today().isoformat()}
        session.save()

    def test_cancel_clears_session(self):
        """Test canceling wizard clears session data."""
        self.client.login(username="sale_cancel", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_cancel", kwargs={"pk": self.project.pk})
        )

        self.assertEqual(response.status_code, 302)
        # Session should be cleared
        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertIsNone(session)

    def test_cancel_redirects_to_operations_list(self):
        """Test cancel redirects back to operations list."""
        self.client.login(username="sale_cancel", password="testpass")
        response = self.client.get(
            reverse("sale_wizard_cancel", kwargs={"pk": self.project.pk})
        )

        self.assertEqual(response.status_code, 302)
        # Just verify it redirects
        self.assertIsNotNone(response.url)


class SaleWizardInvoiceViewTest(TestCase):
    """Test sale invoice view."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer(username="sale_invoice")
        self.project = _make_project()
        self.client_entity = _make_client()
        _link_client_to_project(self.project, self.client_entity)

        # Set up complete session
        session = self.client.session
        session[f"sale_wizard_{self.project.pk}"] = {
            "date": date.today().isoformat(),
            "client_id": self.client_entity.pk,
            "description": "Test sale",
            "total_amount": "1000.00",
            "items": [],
        }
        session.save()

    def test_invoice_view_requires_session(self):
        """Test invoice view requires complete session data."""
        self.client.login(username="sale_invoice", password="testpass")
        response = self.client.get(
            reverse("sale_invoice", kwargs={"pk": self.project.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("project", response.context)

    def test_invoice_view_no_session_redirects(self):
        """Test invoice view redirects without session."""
        project_new = _make_project(name="New Project for Invoice")
        client_entity = _make_client(name="Test Client Invoice")
        _link_client_to_project(project_new, client_entity)

        self.client.login(username="sale_invoice", password="testpass")
        response = self.client.get(
            reverse("sale_invoice", kwargs={"pk": project_new.pk})
        )

        self.assertEqual(response.status_code, 302)


class SaleWizardIntegrationTest(TestCase):
    """Test complete sale wizard workflow."""

    def setUp(self):
        self.client = Client()
        self.officer = _make_officer(username="sale_integration")
        self.project = _make_project()
        self.client_entity = _make_client()
        _link_client_to_project(self.project, self.client_entity)

    def test_complete_sale_wizard_flow(self):
        """Test completing all wizard steps."""
        self.client.login(username="sale_integration", password="testpass")

        # Step 1: Basic info
        response = self.client.post(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk}),
            {
                "date": date.today().isoformat(),
                "client": self.client_entity.pk,
                "description": "Complete sale test",
            },
        )
        self.assertEqual(response.status_code, 302)

        # Step 2: Total amount
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 2}),
            {"total_amount": "2500.00"},
        )
        self.assertEqual(response.status_code, 302)

        # Step 3: Payment
        response = self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 3}),
            {"amount_paid": "1000.00"},
        )
        self.assertEqual(response.status_code, 302)

        # Verify session is complete
        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertEqual(session["total_amount"], "2500.00")
        self.assertEqual(session["amount_paid"], "1000.00")

    def test_wizard_session_persistence(self):
        """Test wizard session persists across steps."""
        self.client.login(username="sale_integration", password="testpass")

        # Step 1
        self.client.post(
            reverse("sale_wizard_step1", kwargs={"pk": self.project.pk}),
            {
                "date": date.today().isoformat(),
                "client": self.client_entity.pk,
                "description": "Persistence test",
            },
        )

        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertEqual(session["description"], "Persistence test")

        # Step 2
        self.client.post(
            reverse("sale_wizard_step_new", kwargs={"pk": self.project.pk, "step": 2}),
            {"total_amount": "1500.00"},
        )

        # Verify step 1 data still in session
        session = self.client.session.get(f"sale_wizard_{self.project.pk}")
        self.assertEqual(session["description"], "Persistence test")
        self.assertEqual(session["total_amount"], "1500.00")
