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

    def test_operation_list_enriches_settlement_values_and_balance(self):
        """Operation list exposes balance, currency and user-friendly settlement data."""
        from decimal import Decimal

        from apps.app_operation.models.proxies import CashInjectionOperation

        world = Entity.create(EntityType.WORLD)
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
        self.assertIn("balance", response.context)
        self.assertIn("currency", response.context)
        self.assertEqual(response.context["currency"], "$")
        self.assertEqual(response.context["balance"], Decimal("100.00"))

        item = response.context["operations"][0]
        for key in ("operation", "kind", "paid", "remaining", "total", "fully_settled", "percent"):
            self.assertIn(key, item)
        self.assertEqual(item["kind"], "one_shot")
        self.assertEqual(item["paid"], Decimal("100.00"))
        self.assertEqual(item["remaining"], Decimal("0.00"))
        self.assertEqual(item["total"], Decimal("100.00"))
        self.assertTrue(item["fully_settled"])
        self.assertEqual(item["percent"], 100)

    def test_operation_list_navigation_shows_entity_display_name(self):
        """Operation list navigation shows the real entity name instead of 'Entity'."""
        self.client.login(username="officer_ops", password="testpass")
        url = reverse("operation_list_view", kwargs={"person_pk": self.person.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        related_titles = [v["title"] for v in response.context["related_views"]]
        self.assertIn("Test Person", related_titles)
        self.assertNotIn("Entity", related_titles)

    def test_operation_list_not_fully_repayed_after_repayment_reversed(self):
        """Reversing a full repayment must un-flag the loan as fully repaid in the list."""
        from decimal import Decimal
        import datetime

        from apps.app_operation.models.proxies import LoanOperation, CashInjectionOperation
        from apps.app_transaction.transaction_type import TransactionType

        world = Entity.create(EntityType.WORLD)
        creditor = Entity.create(EntityType.PERSON, name="List Creditor")
        for target in (creditor, self.person):
            CashInjectionOperation.objects.create(
                source=world,
                destination=target,
                officer=self.officer,
                operation_type=OperationType.CASH_INJECTION,
                amount=Decimal("5000.00"),
                date=datetime.date.today(),
                deletable=False,
            )
        loan = LoanOperation.objects.create(
            source=creditor,
            destination=self.person,
            officer=self.officer,
            operation_type=OperationType.LOAN,
            amount=Decimal("1000.00"),
            date=datetime.date.today(),
            deletable=False,
        )
        # Disburse the full amount so the repayment is backed by a LOAN_PAYMENT.
        loan.create_payment_transaction(
            amount=Decimal("1000.00"),
            officer=self.officer,
            date=datetime.date.today(),
        )
        loan.create_repayment_transaction(
            amount=Decimal("1000.00"),
            officer=self.officer,
            date=datetime.date.today(),
        )
        self.assertTrue(loan.is_fully_repayed)

        repayment = loan.get_all_transactions().get(
            type=TransactionType.LOAN_REPAYMENT, reversal_of__isnull=True
        )
        repayment.reverse(officer=self.officer)

        self.client.login(username="officer_ops", password="testpass")
        url = reverse("operation_list_view", kwargs={"person_pk": self.person.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        loan_item = next(
            item
            for item in response.context["operations"]
            if item["operation"].pk == loan.pk
        )
        self.assertEqual(loan_item["kind"], "repayed")
        self.assertFalse(loan_item["fully_settled"])
        self.assertEqual(loan_item["paid"], Decimal("0.00"))
        self.assertEqual(loan_item["remaining"], Decimal("1000.00"))

    def test_nonexistent_person_returns_404(self):
        """Test that requesting non-existent person returns 404."""
        self.client.login(username="officer_ops", password="testpass")
        url = reverse("operation_list_view", kwargs={"person_pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
