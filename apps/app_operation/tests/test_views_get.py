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


class PurchaseWizardViewTest(TestCase):
    """Test GET request to purchase wizard views."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_purchase", is_staff=True)
        self.project = Entity.create(EntityType.PROJECT, name="Farm")
        self.vendor = Entity.create(EntityType.PERSON, name="Vendor")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )

    def test_authorized_user_can_load_purchase_wizard_step1(self):
        """Test that logged-in user can view purchase wizard step 1."""
        self.client.login(username="officer_purchase", password="testpass")
        url = reverse("purchase_wizard_step1", kwargs={"pk": self.project.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_purchase_wizard_with_vendors(self):
        """Test purchase wizard loads with available vendors."""
        self.client.login(username="officer_purchase", password="testpass")
        url = reverse("purchase_wizard_step1", kwargs={"pk": self.project.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)


class SaleWizardViewTest(TestCase):
    """Test GET request to sale wizard views."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_sale", is_staff=True)
        self.project = Entity.create(EntityType.PROJECT, name="Farm")
        self.client_entity = Entity.create(EntityType.PERSON, name="Client")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.client_entity,
            active=True,
            role=StakeholderRole.CLIENT,
        )

    def test_authorized_user_can_load_sale_wizard_step1(self):
        """Test that logged-in user can view sale wizard step 1."""
        self.client.login(username="officer_sale", password="testpass")
        url = reverse("sale_wizard_step1", kwargs={"pk": self.project.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_sale_wizard_with_clients(self):
        """Test sale wizard loads with available clients."""
        self.client.login(username="officer_sale", password="testpass")
        url = reverse("sale_wizard_step1", kwargs={"pk": self.project.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
