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
from apps.app_operation.models.proxies import (
    CapitalGainOperation,
    CashInjectionOperation,
    LoanOperation,
    PurchaseOperation,
    SaleOperation,
)
from apps.app_transaction.transaction_type import TransactionType


class OperationDetailViewTest(TestCase):
    """Test GET request to operation detail view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_op_detail", is_staff=True)
        from apps.app_operation.models.operation_type import OperationType
        from apps.app_operation.models.proxies import CashInjectionOperation
        from decimal import Decimal
        import datetime

        self.world = Entity.create(EntityType.WORLD)
        self.destination = Entity.create(EntityType.PERSON, name="Destination")
        self.operation = CashInjectionOperation.objects.create(
            source=self.world,
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

    def test_operation_detail_navigation_shows_real_entity_names(self):
        """Navigation links use the real source/destination names instead of generic labels."""
        from apps.app_operation.models.proxies import PurchaseOperation
        from decimal import Decimal
        import datetime

        self.client.login(username="officer_op_detail", password="testpass")
        vendor = Entity.create(
            EntityType.PERSON, name="Alpha Feed Supplier", is_vendor=True
        )
        project = Entity.create(EntityType.PROJECT, name="Beta Farms Project")
        Stakeholder.objects.create(
            parent=project,
            target=vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        operation = PurchaseOperation.objects.create(
            source=project,
            destination=vendor,
            officer=self.officer,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("100.00"),
            date=datetime.date.today(),
            deletable=False,
        )

        url = reverse("operation_detail_view", kwargs={"pk": operation.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, reverse("entity_detail", kwargs={"pk": project.pk})
        )
        self.assertContains(
            response, reverse("entity_detail", kwargs={"pk": vendor.pk})
        )
        self.assertContains(response, "Alpha Feed Supplier")
        self.assertContains(response, "Beta Farms Project")
        self.assertNotContains(response, "Source Entity")
        self.assertNotContains(response, "Destination Entity")

    def test_operation_detail_hides_virtual_entity_links(self):
        """Virtual (world/system) source entities get no navigation link."""
        self.client.login(username="officer_op_detail", password="testpass")
        url = reverse("operation_detail_view", kwargs={"pk": self.operation.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # The world source is virtual: no navigation link to its detail page
        self.assertNotContains(
            response, reverse("entity_detail", kwargs={"pk": self.operation.source.pk})
        )
        # The generic placeholder label must not leak into the UI either
        self.assertNotContains(response, "Source Entity")
        # The real destination link is still present with its name
        self.assertContains(
            response,
            reverse("entity_detail", kwargs={"pk": self.operation.destination.pk}),
        )
        self.assertContains(response, "Destination")

    def test_nonexistent_operation_returns_404(self):
        """Test that requesting non-existent operation returns 404."""
        self.client.login(username="officer_op_detail", password="testpass")
        url = reverse("operation_detail_view", kwargs={"pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_operation_detail_shows_both_sides_operations_list_links(self):
        """The navigation bar links to the operations list of both real counterparts."""
        from decimal import Decimal
        import datetime

        self.client.login(username="officer_op_detail", password="testpass")
        vendor = Entity.create(
            EntityType.PERSON, name="Nav Vendor", is_vendor=True
        )
        project = Entity.create(EntityType.PROJECT, name="Nav Project")
        Stakeholder.objects.create(
            parent=project,
            target=vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        operation = PurchaseOperation.objects.create(
            source=project,
            destination=vendor,
            officer=self.officer,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("100.00"),
            date=datetime.date.today(),
            deletable=False,
        )

        url = reverse("operation_detail_view", kwargs={"pk": operation.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, reverse("operation_list_view", kwargs={"person_pk": project.pk})
        )
        self.assertContains(
            response, reverse("operation_list_view", kwargs={"person_pk": vendor.pk})
        )

    def test_operation_detail_exempts_virtual_entity_operations_link(self):
        """Virtual (system/world) counterparts get no operations-list link."""
        self.client.login(username="officer_op_detail", password="testpass")
        url = reverse("operation_detail_view", kwargs={"pk": self.operation.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # The world source is virtual — no operations list link for it.
        self.assertNotContains(
            response,
            reverse(
                "operation_list_view",
                kwargs={"person_pk": self.operation.source.pk},
            ),
        )
        # The real destination link is still present.
        self.assertContains(
            response,
            reverse(
                "operation_list_view",
                kwargs={"person_pk": self.destination.pk},
            ),
        )

    def _make_repayable_loan(self, **kwargs):
        """Create a seeded loan that supports repayment recording."""
        from decimal import Decimal
        import datetime

        world = self.world
        creditor = Entity.create(EntityType.PERSON, name="Loan Creditor")
        debtor = Entity.create(EntityType.PERSON, name="Loan Debtor")
        for target in (creditor, debtor):
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
            destination=debtor,
            officer=self.officer,
            operation_type=OperationType.LOAN,
            amount=Decimal("1000.00"),
            date=datetime.date.today(),
            deletable=False,
        )
        # Disburse the full amount so repayments are backed by a LOAN_PAYMENT.
        loan.create_payment_transaction(
            amount=Decimal("1000.00"),
            officer=self.officer,
            date=datetime.date.today(),
        )
        return loan, creditor

    def test_operation_detail_hides_record_repayment_when_fully_repayed(self):
        """The 'Record Repayment' action is hidden once the operation is fully repaid."""
        from decimal import Decimal
        import datetime

        self.client.login(username="officer_op_detail", password="testpass")
        loan, _ = self._make_repayable_loan()
        loan.create_repayment_transaction(
            amount=Decimal("1000.00"),
            officer=self.officer,
            date=datetime.date.today(),
        )
        self.assertTrue(loan.is_fully_repayed)

        url = reverse("operation_detail_view", kwargs={"pk": loan.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, reverse("record_transaction_repayment", kwargs={"pk": loan.pk})
        )

    def test_operation_detail_shows_record_repayment_when_not_fully_repayed(self):
        """The 'Record Repayment' action stays visible while repayment is outstanding."""
        from decimal import Decimal
        import datetime

        self.client.login(username="officer_op_detail", password="testpass")
        loan, _ = self._make_repayable_loan()
        loan.create_repayment_transaction(
            amount=Decimal("400.00"),
            officer=self.officer,
            date=datetime.date.today(),
        )
        self.assertFalse(loan.is_fully_repayed)

        url = reverse("operation_detail_view", kwargs={"pk": loan.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, reverse("record_transaction_repayment", kwargs={"pk": loan.pk})
        )

    def test_operation_detail_shows_record_repayment_after_repayment_reversed(self):
        """Reversing a full repayment must un-mark the loan and restore the action."""
        from decimal import Decimal
        import datetime

        self.client.login(username="officer_op_detail", password="testpass")
        loan, _ = self._make_repayable_loan()
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

        url = reverse("operation_detail_view", kwargs={"pk": loan.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, reverse("record_transaction_repayment", kwargs={"pk": loan.pk})
        )

    def _make_payable_purchase(self):
        """Create a purchase whose project is funded so payments can be recorded."""
        from decimal import Decimal
        import datetime

        system = Entity.create(EntityType.SYSTEM)
        vendor = Entity.create(
            EntityType.PERSON, name="Pay Vendor", is_vendor=True
        )
        project = Entity.create(EntityType.PROJECT, name="Pay Project")
        Stakeholder.objects.create(
            parent=project,
            target=vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        CapitalGainOperation.objects.create(
            source=system,
            destination=project,
            officer=self.officer,
            operation_type=OperationType.CAPITAL_GAIN,
            amount=Decimal("5000.00"),
            date=datetime.date.today(),
            deletable=False,
        )
        return PurchaseOperation.objects.create(
            source=project,
            destination=vendor,
            officer=self.officer,
            operation_type=OperationType.PURCHASE,
            amount=Decimal("1000.00"),
            date=datetime.date.today(),
            deletable=False,
        )

    def test_operation_detail_hides_record_payment_when_fully_settled(self):
        """The 'Record Payment' action is hidden once the operation is fully paid."""
        from decimal import Decimal
        import datetime

        self.client.login(username="officer_op_detail", password="testpass")
        operation = self._make_payable_purchase()
        operation.create_payment_transaction(
            amount=Decimal("1000.00"),
            officer=self.officer,
            date=datetime.date.today(),
        )
        self.assertTrue(operation.is_fully_settled)

        url = reverse("operation_detail_view", kwargs={"pk": operation.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            reverse("record_transaction_payment", kwargs={"pk": operation.pk}),
        )

    def test_operation_detail_shows_record_payment_when_not_fully_settled(self):
        """The 'Record Payment' action stays visible while a balance is outstanding."""
        self.client.login(username="officer_op_detail", password="testpass")
        operation = self._make_payable_purchase()
        self.assertFalse(operation.is_fully_settled)

        url = reverse("operation_detail_view", kwargs={"pk": operation.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("record_transaction_payment", kwargs={"pk": operation.pk}),
        )
