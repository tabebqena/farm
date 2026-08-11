"""GET request tests for app_entity views.

Tests that ensure authorized users can make GET requests to pages without errors.
"""

from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.app_entity.models import Entity, EntityType, Stakeholder, StakeholderRole
from apps.app_entity.models.category import (
    FinancialCategoriesEntitiesRelations,
    FinancialCategory,
)
from apps.app_inventory.models import ProductLedgerEntry
from apps.app_inventory.tests.general import make_product, make_product_template, make_user
from apps.app_operation.models.operation_type import OperationType
from apps.app_operation.models.proxies import CapitalGainOperation, ExpenseOperation


class EntityDetailViewTest(TestCase):
    """Test GET request to entity detail view."""

    def setUp(self):
        self.client = Client()
        self.officer = make_user(username="officer_detail", is_staff=True)
        self.entity = Entity.create(EntityType.PROJECT, name="Test Project")

    def test_authorized_user_can_load_entity_detail(self):
        """Test that logged-in user can view entity detail."""
        self.client.login(username="officer_detail", password="testpass")
        url = reverse("entity_detail", kwargs={"pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("entity", response.context)
        self.assertEqual(response.context["entity"], self.entity)

    def test_entity_detail_with_stakeholders(self):
        """Test entity detail view loads with stakeholders."""
        vendor = Entity.create(EntityType.PERSON, name="Vendor")
        Stakeholder.objects.create(
            parent=self.entity,
            target=vendor,
            active=True,
            role=StakeholderRole.VENDOR,
        )

        self.client.login(username="officer_detail", password="testpass")
        url = reverse("entity_detail", kwargs={"pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("entity", response.context)

    def test_entity_detail_navigation_keeps_operations_and_periods_links(self):
        """Entity detail navigation keeps Operations/Periods links (regression)."""
        self.client.login(username="officer_detail", password="testpass")
        url = reverse("entity_detail", kwargs={"pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("operation_list_view", kwargs={"person_pk": self.entity.pk}),
        )
        self.assertContains(
            response,
            reverse("period_list_view", kwargs={"entity_pk": self.entity.pk}),
        )

    def test_nonexistent_entity_detail_returns_404(self):
        """Test that requesting non-existent entity returns 404."""
        self.client.login(username="officer_detail", password="testpass")
        url = reverse("entity_detail", kwargs={"pk": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_redirected_from_entity_detail(self):
        """Test that unauthenticated users are redirected from entity detail."""
        url = reverse("entity_detail", kwargs={"pk": self.entity.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_entity_detail_context_has_financial_summary(self):
        """Entity detail context exposes payables, receivables, and stock value."""
        self.client.login(username="officer_detail", password="testpass")
        url = reverse("entity_detail", kwargs={"pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        for key in ("payables", "receivables", "stock_value", "currency"):
            self.assertIn(key, response.context)
        self.assertEqual(response.context["payables"], self.entity.payables)
        self.assertEqual(response.context["receivables"], self.entity.receivables)
        self.assertEqual(
            response.context["stock_value"],
            ProductLedgerEntry.inventory_value_at(self.entity, date.today()),
        )

    def test_entity_detail_reflects_payables(self):
        """Payables from an expense issuance appear in the entity detail context."""
        system = Entity.create(EntityType.SYSTEM)
        world = Entity.create(EntityType.WORLD)
        CapitalGainOperation(
            source=system,
            destination=self.entity,
            amount=Decimal("5000.00"),
            operation_type=OperationType.CAPITAL_GAIN,
            date=date.today(),
            description="Seed",
            officer=self.officer,
        ).save()
        category, _ = FinancialCategory.objects.get_or_create(
            name="Test Expense",
            aspect="General",
            defaults={"category_type": "EXPENSE"},
        )
        FinancialCategoriesEntitiesRelations.objects.get_or_create(
            entity=self.entity, category=category, defaults={"max_limit": Decimal("0.00")}
        )
        ExpenseOperation(
            source=self.entity,
            destination=world,
            amount=Decimal("1000.00"),
            operation_type=OperationType.EXPENSE,
            date=date.today(),
            description="Test expense",
            officer=self.officer,
            category=category,
        ).save()

        self.client.login(username="officer_detail", password="testpass")
        url = reverse("entity_detail", kwargs={"pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.context["payables"], Decimal("0.00"))
        self.assertEqual(response.context["payables"], self.entity.payables)

    def test_entity_detail_reflects_stock_value(self):
        """Stock value from product ledger entries appears in the entity detail context."""
        template = make_product_template("Calves")
        template.entities.add(self.entity)
        product = make_product(template, unit_price=Decimal("100.00"), quantity=1, entity=self.entity)
        ProductLedgerEntry.objects.create(
            product=product,
            entry_type=ProductLedgerEntry.EntryType.PURCHASE_MOVEMENT,
            date=date.today(),
            quantity_delta=Decimal("1.00"),
            value_delta=Decimal("100.00"),
            idempotency_key="entity_detail_stock_value_test",
        )

        self.client.login(username="officer_detail", password="testpass")
        url = reverse("entity_detail", kwargs={"pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stock_value"], Decimal("100.00"))
        self.assertEqual(
            response.context["stock_value"],
            ProductLedgerEntry.inventory_value_at(self.entity, date.today()),
        )

    def test_entity_detail_financial_summary_links_and_balance(self):
        """Financial summary card shows current balance and links to payables/receivables."""
        self.client.login(username="officer_detail", password="testpass")
        url = reverse("entity_detail", kwargs={"pk": self.entity.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Financial Summary")
        self.assertContains(response, "Current Balance")
        self.assertContains(
            response,
            reverse("entity_payables_list", kwargs={"entity_pk": self.entity.pk}),
        )
        self.assertContains(
            response,
            reverse("entity_receivables_list", kwargs={"entity_pk": self.entity.pk}),
        )
