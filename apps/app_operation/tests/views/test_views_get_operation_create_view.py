"""GET request tests verifying the current fund balance of the source entity.

Every operation create page and transaction (payment / repayment) create page
should display the current fund of the entity the money comes from:

- For most operations the source is the URL (project) entity, so the fund shown
  is the project balance.
- For operations whose source is a "post" entity (e.g. Sale's client) the source
  is only known once chosen, so the create page falls back to the URL entity's
  fund until then.
- Payment transactions debit ``operation.payment_source_fund``.
- Repayment transactions debit ``operation.payment_target_fund``.
"""

from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_inventory.tests.general import make_user
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import (
    CorrectionCreditOperation,
    CashInjectionOperation,
    LoanOperation,
    PurchaseOperation,
)


def _get_or_create_system():
    try:
        return Entity.objects.get(entity_type=EntityType.SYSTEM)
    except Entity.DoesNotExist:
        return Entity.create(EntityType.SYSTEM)


def _inject_funds(entity, amount, officer):
    """Add real cash funds to a project entity via a CorrectionCreditOperation.

    A CapitalGain is non-cash (its *_PAYMENT is excluded from payment_types()),
    so it cannot fund the entity's spendable balance.
    """
    system = _get_or_create_system()
    CorrectionCreditOperation(
        source=system,
        destination=entity,
        amount=amount,
        operation_type=OperationType.CORRECTION_CREDIT,
        date=timezone.now().date(),
        description="Fund injection",
        officer=officer,
    ).save()


def _inject_person_funds(entity, amount, officer):
    """Add funds to a person entity via a CashInjectionOperation."""
    world = Entity.objects.filter(entity_type=EntityType.WORLD).first()
    if not world:
        world = Entity.create(EntityType.WORLD)
    CashInjectionOperation(
        source=world,
        destination=entity,
        amount=amount,
        operation_type=OperationType.CASH_INJECTION,
        date=timezone.now().date(),
        description="Fund injection",
        officer=officer,
    ).save()


class OperationCreateViewSourceFundTests(TestCase):
    """The generic operation create page shows the source entity's fund balance."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_create", is_staff=True)
        self.project = Entity.create(EntityType.PROJECT, name="Project")
        _inject_funds(self.project, Decimal("1000.00"), self.officer)
        self.client.login(username="officer_create", password="testpass")

    def _get_create(self, op_type):
        return self.client.get(
            reverse(
                "operation_create_view",
                kwargs={"pk": self.project.pk, "op_type": op_type},
            )
        )

    def test_purchase_create_exposes_source_fund(self):
        """Purchase source is the project (url entity) → fund is the project balance."""
        response = self._get_create("purchase")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["source_entity"], self.project)
        self.assertEqual(response.context["source_balance"], self.project.balance)
        self.assertEqual(response.context["currency"], "$")

    def test_purchase_create_renders_current_fund(self):
        """The create form renders the source fund balance to the user."""
        response = self._get_create("purchase")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Source Fund", content)
        self.assertIn(self.project.name, content)
        self.assertIn("1000.00", content)

    def test_expense_create_source_fund_is_project(self):
        """Expense source is the project → fund is the project balance."""
        response = self._get_create("expense")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["source_entity"], self.project)
        self.assertEqual(response.context["source_balance"], self.project.balance)

    def test_sale_create_redirects_to_sale_wizard(self):
        """SALE is only created through the sale wizard — the generic create view
        redirects to it (there is no second sale path)."""
        response = self._get_create("sale")
        self.assertEqual(response.status_code, 302)
        self.assertIn("sale", response.url)

    def test_worker_advance_create_source_fund_is_project(self):
        """Worker advance source is the project → fund is the project balance."""
        response = self._get_create("worker-advance")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["source_entity"], self.project)
        self.assertEqual(response.context["source_balance"], self.project.balance)


class TransactionCreateViewSourceFundTests(TestCase):
    """Payment / repayment create pages expose the source fund balance."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_txn", is_staff=True)
        self.vendor = Entity.create(EntityType.PERSON, name="Vendor", is_vendor=True)
        self.project = Entity.create(EntityType.PROJECT, name="Project")
        Stakeholder.objects.create(
            parent=self.project,
            target=self.vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )
        _inject_funds(self.project, Decimal("2000.00"), self.officer)
        self.client.login(username="officer_txn", password="testpass")

    def test_payment_create_exposes_source_fund(self):
        """Payment debits the project fund (the operation's payment source fund)."""
        op = PurchaseOperation.objects.create(
            source=self.project,
            destination=self.vendor,
            amount=Decimal("1000.00"),
            operation_type=OperationType.PURCHASE,
            date=date.today(),
            officer=self.officer,
            deletable=False,
        )
        url = reverse("record_transaction_payment", kwargs={"pk": op.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["source_entity"], self.project)
        self.assertEqual(response.context["source_balance"], self.project.balance)

        content = response.content.decode()
        self.assertIn("Paying Fund", content)
        self.assertIn("2000.00", content)

    def test_repayment_create_exposes_source_fund(self):
        """Repayment debits the operation's payment target fund (the debtor)."""
        lender = Entity.create(EntityType.PERSON, name="Lender")
        borrower = Entity.create(EntityType.PERSON, name="Borrower")
        _inject_person_funds(borrower, Decimal("500.00"), self.officer)
        op = LoanOperation.objects.create(
            source=lender,
            destination=borrower,
            amount=Decimal("2000.00"),
            operation_type=OperationType.LOAN,
            date=date.today(),
            officer=self.officer,
            deletable=False,
        )
        url = reverse("record_transaction_repayment", kwargs={"pk": op.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["source_entity"], borrower)
        self.assertEqual(response.context["source_balance"], borrower.balance)

        content = response.content.decode()
        self.assertIn("Repaying Fund", content)
        self.assertIn("500.00", content)
